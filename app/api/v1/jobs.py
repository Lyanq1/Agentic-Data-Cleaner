"""Job management endpoints."""
import asyncio
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from app.api.dependencies import get_file_service, get_graph_service, get_job_service
from app.models.db.job import JobStatus
from app.models.schemas.job import JobCreate, JobListResponse, JobResponse
from app.services.file_service import FileService
from app.services.graph_service import GraphService
from app.services.job_service import JobService
from app.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


async def _run_graph_background(
    job_id: str,
    file_path: str,
    rules: dict,
    job_svc: JobService,
    graph_svc: GraphService,
) -> None:
    """Background task: invoke graph and update job status."""
    try:
        await job_svc.update_status(job_id, JobStatus.RUNNING, thread_id=job_id)
        final_state = await graph_svc.invoke(job_id, file_path, rules)
        # Check if graph paused for HITL
        if final_state.get("waiting_for_human"):
            await job_svc.update_status(
                job_id,
                JobStatus.WAITING_FOR_HUMAN,
                hitl_waiting_node=final_state.get("hitl_node"),
            )
        else:
            await job_svc.update_status(
                job_id,
                JobStatus.COMPLETED,
                result={
                    k: final_state.get(k)
                    for k in ("profile_result", "clean_result", "validation_result", "transform_result", "report_result")
                },
            )
    except Exception as e:
        logger.error("Graph execution failed", job_id=job_id, error=str(e))
        await job_svc.update_status(job_id, JobStatus.FAILED, error_message=str(e))


@router.post("/", status_code=status.HTTP_202_ACCEPTED, response_model=JobResponse, summary="Create and start a new job")
async def create_job(
    payload: JobCreate,
    background_tasks: BackgroundTasks,
    job_svc: JobService = Depends(get_job_service),
    graph_svc: GraphService = Depends(get_graph_service),
    file_svc: FileService = Depends(get_file_service),
) -> JobResponse:
    """Create a new data cleaning job and start the agent pipeline."""
    job = await job_svc.create_job(payload)
    background_tasks.add_task(
        _run_graph_background,
        job.id, payload.file_path, payload.rules, job_svc, graph_svc,
    )
    return JobResponse.model_validate(job)


@router.get("/{job_id}", response_model=JobResponse, summary="Get job status and result")
async def get_job(
    job_id: str,
    job_svc: JobService = Depends(get_job_service),
) -> JobResponse:
    """Retrieve a job by ID."""
    job = await job_svc.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return JobResponse.model_validate(job)


@router.get("/", response_model=JobListResponse, summary="List all jobs")
async def list_jobs(
    page: int = 1,
    page_size: int = 20,
    job_svc: JobService = Depends(get_job_service),
) -> JobListResponse:
    """Paginated list of all jobs."""
    jobs, total = await job_svc.list_jobs(page=page, page_size=page_size)
    return JobListResponse(
        items=[JobResponse.model_validate(j) for j in jobs],
        total=total, page=page, page_size=page_size,
    )


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Cancel a job")
async def cancel_job(
    job_id: str,
    job_svc: JobService = Depends(get_job_service),
) -> None:
    """Cancel a pending or running job."""
    job = await job_svc.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    await job_svc.update_status(job_id, JobStatus.CANCELLED)
