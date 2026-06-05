"""Debug API for running the deduplication agent against a saved pipeline state."""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.pipeline import run_dedup_agent_for_run

logger = logging.getLogger(__name__)
router = APIRouter()


class DedupRunRequest(BaseModel):
    """Request body for direct dedup agent execution."""

    run_id: str
    key_columns: list[str] = Field(default_factory=list)


@router.post("/dedup/run", summary="Run the deduplication agent for an existing pipeline run")
async def api_run_dedup(request: DedupRunRequest):
    """Load checkpointed state by run_id and execute the dedup agent directly."""
    try:
        result = await run_dedup_agent_for_run(
            run_id=request.run_id,
            key_columns=request.key_columns,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Failed to run dedup agent for run_id=%s: %s", request.run_id, exc)
        raise HTTPException(status_code=500, detail=f"Failed to run dedup agent: {exc}")

    if result is None:
        raise HTTPException(status_code=404, detail=f"Run '{request.run_id}' not found.")

    return result
