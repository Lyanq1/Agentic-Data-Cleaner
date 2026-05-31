"""Pipeline API — upload dataset, run pipeline, check state."""
import uuid
import logging

from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from app.exceptions.ingestion_exceptions import IngestionError
from app.services.ingestion import get_ingestion_service
from app.services.pipeline import run_pipeline, get_pipeline_state

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/pipeline/run", summary="Upload dataset and run the cleaning pipeline")
async def api_run_pipeline(
    file: UploadFile = File(..., description="Dataset file (CSV, TSV, Excel, JSON, JSONL)"),
    user_prompt: str = Form(default="", description="Optional cleaning instruction"),
):
    """Upload a dataset, convert to canonical Parquet, then run profiler → input_validator.

    Returns a ``run_id`` that can be used to check state later via ``GET /pipeline/{run_id}/state``.
    """
    contents = await file.read()

    # Ingestion: validate → save → convert to Parquet
    ingestion = get_ingestion_service()
    try:
        ingestion.validate(file.filename, contents)
        result = ingestion.save_and_convert(file.filename, contents)
    except IngestionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Run pipeline
    run_id = uuid.uuid4().hex[:12]
    try:
        pipeline_result = await run_pipeline(
            run_id=run_id,
            canonical_path=result.canonical_path,
            input_format=result.input_format,
            user_prompt=user_prompt,
            original_filename=result.original_filename,
            data_schema=result.data_schema,
        )
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise HTTPException(status_code=500, detail=f"Pipeline execution failed: {e}")

    return pipeline_result


@router.get("/pipeline/{run_id}/state", summary="Get current state of a pipeline run")
async def api_get_pipeline_state(run_id: str):
    """Retrieve the current state of a pipeline run by its ``run_id``.

    Reads directly from the Postgres checkpointer — reflects the latest snapshot.
    """
    try:
        state = await get_pipeline_state(run_id)
    except Exception as e:
        logger.error(f"Failed to retrieve state for run_id={run_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve state: {e}")

    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    return state
