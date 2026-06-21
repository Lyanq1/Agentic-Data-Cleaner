"""Debug API for running the deduplication agent against a saved pipeline state."""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agents.deduplication.models import DeduplicationHitlFeedback
from app.services.pipeline import run_dedup_agent_for_run, submit_dedup_hitl_feedback

logger = logging.getLogger(__name__)
router = APIRouter()


class DedupRunRequest(BaseModel):
    """Request body for direct dedup agent execution."""

    run_id: str


@router.post("/dedup/run", summary="Run the deduplication agent for an existing pipeline run")
async def api_run_dedup(request: DedupRunRequest):
    """Load checkpointed state by run_id and execute the dedup agent directly."""
    try:
        result = await run_dedup_agent_for_run(
            run_id=request.run_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Failed to run dedup agent for run_id=%s: %s", request.run_id, exc)
        raise HTTPException(status_code=500, detail=f"Failed to run dedup agent: {exc}")

    if result is None:
        raise HTTPException(status_code=404, detail=f"Run '{request.run_id}' not found.")

    return result


@router.post("/dedup/review/{run_id}", summary="Submit HITL strategy review choices for a dedup run")
async def api_submit_dedup_review(run_id: str, request: DeduplicationHitlFeedback):
    """Persist human strategy review choices for a dedup run without rerunning the agent."""
    try:
        result = await submit_dedup_hitl_feedback(run_id=run_id, feedback=request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Failed to submit dedup review for run_id=%s: %s", run_id, exc)
        raise HTTPException(status_code=500, detail=f"Failed to submit dedup review: {exc}")

    if result is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    return result
