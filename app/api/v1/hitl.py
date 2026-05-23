"""Human-in-the-Loop (HITL) resume endpoint."""
from fastapi import APIRouter, Depends, HTTPException
from app.api.dependencies import get_graph_service, get_job_service
from app.models.db.job import JobStatus
from app.models.schemas.job import JobResumeRequest, JobResponse
from app.services.graph_service import GraphService
from app.services.job_service import JobService
from app.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.post(
    "/{job_id}/resume",
    response_model=JobResponse,
    summary="Resume a paused job (HITL approval/rejection)",
)
async def resume_job(
    job_id: str,
    payload: JobResumeRequest,
    job_svc: JobService = Depends(get_job_service),
    graph_svc: GraphService = Depends(get_graph_service),
) -> JobResponse:
    """Resume a graph paused at a HITL interrupt node.

    - approved=true → graph continues to next step
    - approved=false → graph terminates with rejection
    """
    job = await job_svc.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    if job.status != JobStatus.WAITING_FOR_HUMAN:
        raise HTTPException(
            status_code=400,
            detail=f"Job '{job_id}' is not waiting for human input (status: {job.status})",
        )
    try:
        final_state = await graph_svc.resume(
            job_id=job_id,
            approved=payload.approved,
            feedback=payload.feedback,
        )
        if payload.approved:
            await job_svc.update_status(
                job_id,
                JobStatus.COMPLETED if not final_state.get("waiting_for_human") else JobStatus.WAITING_FOR_HUMAN,
                result=final_state.get("report_result"),
                hitl_waiting_node=final_state.get("hitl_node") if final_state.get("waiting_for_human") else None,
            )
        else:
            await job_svc.update_status(job_id, JobStatus.CANCELLED, error_message="Rejected by user")
    except Exception as e:
        logger.error("HITL resume failed", job_id=job_id, error=str(e))
        await job_svc.update_status(job_id, JobStatus.FAILED, error_message=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e
    job = await job_svc.get_job(job_id)
    return JobResponse.model_validate(job)
