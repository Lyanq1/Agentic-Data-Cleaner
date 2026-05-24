"""Server-Sent Events (SSE) streaming endpoint for live graph updates."""
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from app.api.dependencies import get_graph_service, get_job_service
from app.core.constants import JobStatus
from app.services.graph.graph_service import GraphService
from app.services.job.job_service import JobService

router = APIRouter()


@router.get(
    "/{job_id}/stream",
    summary="Stream live graph execution events (SSE)",
    response_class=StreamingResponse,
)
async def stream_job(
    job_id: str,
    job_svc: JobService = Depends(get_job_service),
    graph_svc: GraphService = Depends(get_graph_service),
):
    """Stream real-time graph node updates as Server-Sent Events.

    Each event is a JSON-encoded state delta from LangGraph's astream().
    """
    job = await job_svc.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    async def event_generator():
        try:
            async for event in graph_svc.stream(
                job_id=job_id,
                file_path=job.input_file_path or "",
                rules=job.job_metadata or {},
            ):
                data = json.dumps(event, default=str)
                yield f"data: {data}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
