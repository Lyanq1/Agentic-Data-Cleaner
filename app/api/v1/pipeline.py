"""Pipeline API — upload dataset, run pipeline, check state."""
import io
import uuid
import logging

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage

from app.exceptions.ingestion_exceptions import IngestionError
from app.services.dataframe_order import restore_original_column_order
from app.services.lineage_service import LineageService
from app.services.lineage_utils import resolve_lineage_session_id
from app.services.ingestion import get_ingestion_service
from app.services.pipeline import run_pipeline, get_pipeline_state
from app.graphs.graph import build_graph
from app.graphs.checkpointer import get_checkpointer_manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/pipeline/run", summary="Upload dataset and run the cleaning pipeline")
async def api_run_pipeline(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Dataset file (CSV, TSV, Excel, JSON, JSONL)"),
    clean_file: UploadFile | None = File(None, description="Optional ground truth file for testing"),
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

    clean_dataset_path = None
    if clean_file:
        clean_contents = await clean_file.read()
        try:
            ingestion.validate(clean_file.filename, clean_contents)
            # Write directly to disk to avoid bottlenecking the process with parsing
            from app.config.config import get_settings
            from pathlib import Path
            upload_dir = Path(get_settings().upload_dir)
            upload_dir.mkdir(parents=True, exist_ok=True)
            clean_path = upload_dir / f"clean_{clean_file.filename}"
            clean_path.write_bytes(clean_contents)
            clean_dataset_path = str(clean_path)
        except IngestionError as e:
            logger.warning(f"Failed to process clean file: {e}")

    # Run pipeline in background
    run_id = uuid.uuid4().hex[:12]
    background_tasks.add_task(
        run_pipeline,
        run_id=run_id,
        canonical_path=result.canonical_path,
        input_format=result.input_format,
        user_prompt=user_prompt,
        original_filename=result.original_filename,
        data_schema=result.data_schema,
        clean_dataset_path=clean_dataset_path,
    )

    return {
        "run_id": run_id,
        "message": "Pipeline execution started in the background.",
        "original_filename": result.original_filename,
        "input_format": result.input_format,
        "canonical_path": result.canonical_path,
    }


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


def _load_latest_processed_dataframe(state: dict):
    """Load the latest processed dataframe from lineage, falling back to canonical parquet."""
    session_id = resolve_lineage_session_id(state)
    if session_id:
        df = LineageService.get_latest_version(session_id)
        if not df.empty:
            return restore_original_column_order(df, state)

    dataset_path = state.get("dataset_path")
    if dataset_path:
        import pandas as pd

        return pd.read_parquet(dataset_path)

    return None


def _json_safe_preview_value(value):
    """Convert dataframe preview values to JSON-safe scalars."""
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe_preview_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe_preview_value(item) for item in value]
    return value


@router.get("/pipeline/{run_id}/download", summary="Download latest processed dataset")
async def api_download_processed_dataset(run_id: str, format: str = "parquet"):
    """Export the latest processed lineage version as CSV, XLSX, or Parquet."""
    state = await get_pipeline_state(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    try:
        df = _load_latest_processed_dataframe(state)
    except Exception as e:
        logger.error(f"Failed to load processed dataset for run_id={run_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load processed dataset: {e}")

    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="No processed dataset available to download.")

    export_format = format.lower()
    if export_format not in {"csv", "xlsx", "parquet"}:
        raise HTTPException(status_code=400, detail="Unsupported format. Use csv, xlsx, or parquet.")

    buffer = io.BytesIO()
    try:
        if export_format == "csv":
            buffer.write(df.to_csv(index=False).encode("utf-8-sig"))
            media_type = "text/csv"
            extension = "csv"
        elif export_format == "xlsx":
            df.to_excel(buffer, index=False, engine="openpyxl")
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            extension = "xlsx"
        else:
            df.to_parquet(buffer, index=False, engine="pyarrow")
            media_type = "application/octet-stream"
            extension = "parquet"
    except Exception as e:
        logger.error(f"Failed to export processed dataset for run_id={run_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to export processed dataset: {e}")
    buffer.seek(0)

    filename = f"{run_id}_processed.{extension}"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(buffer, media_type=media_type, headers=headers)


@router.get("/pipeline/{run_id}/preview", summary="Preview latest processed dataset")
async def api_preview_processed_dataset(run_id: str, limit: int = 50):
    """Return a small JSON preview of the latest processed lineage version."""
    state = await get_pipeline_state(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    try:
        df = _load_latest_processed_dataframe(state)
    except Exception as e:
        logger.error(f"Failed to load processed preview for run_id={run_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load processed preview: {e}")

    if df is None or df.empty:
        return {
            "columns": [],
            "rows": [],
            "row_count": 0,
            "preview_count": 0,
        }

    safe_limit = max(1, min(limit, 200))
    preview_df = df.head(safe_limit).where(df.head(safe_limit).notna(), None)
    rows = [
        {str(key): _json_safe_preview_value(value) for key, value in row.items()}
        for row in preview_df.to_dict(orient="records")
    ]
    return {
        "columns": [str(col) for col in df.columns],
        "rows": rows,
        "row_count": int(len(df)),
        "preview_count": int(len(preview_df)),
    }


class ResolveRequest(BaseModel):
    answers: dict[str, str]


@router.post("/pipeline/{run_id}/resolve", summary="Submit clarification answers and resume pipeline")
async def api_resolve_pipeline(
    run_id: str,
    payload: ResolveRequest,
    background_tasks: BackgroundTasks,
):
    """Update checkpointer state with user's answers and resume the cleaning pipeline."""
    config = {"configurable": {"thread_id": run_id}}
    
    async with get_checkpointer_manager().get() as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        snapshot = await graph.aget_state(config)
        
        if not snapshot or not snapshot.values:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
        
        state = snapshot.values
        val_result = state.get("input_validation_result")
        if not val_result:
            raise HTTPException(status_code=400, detail="No input validation result found to resolve.")
            
        # Convert val_result to dict if it is a Pydantic model or other object
        if hasattr(val_result, "model_dump"):
            val_result_dict = val_result.model_dump()
        elif hasattr(val_result, "dict"):
            val_result_dict = val_result.dict()
        else:
            val_result_dict = dict(val_result)
            
        clarifications = val_result_dict.get("clarifications")
        if not clarifications:
            raise HTTPException(status_code=400, detail="No clarifications found in input validation result.")
            
        # Update the answer field in clarifications
        # payload.answers is e.g. {"null.Q1_strategy": "Option A: ...", ...}
        for key, answer in payload.answers.items():
            parts = key.split(".")
            if len(parts) == 2:
                cat, q_key = parts
                cat_data = clarifications.get(cat)
                if cat_data:
                    q_data = cat_data.get(q_key)
                    if q_data:
                        q_data["answer"] = answer
        
        # Build HumanMessage summarizing answers for the LLM chat history
        summary_lines = ["Here are my decisions for the clarification questions:"]
        for key, answer in payload.answers.items():
            summary_lines.append(f"- {key}: {answer}")
        summary_msg = HumanMessage(content="\n".join(summary_lines))
        
        # Prepare state updates
        state_updates = {
            "input_validation_result": val_result_dict,
            "messages": [summary_msg]
        }
        
        # Update the thread state in checkpointer
        await graph.aupdate_state(config, state_updates, as_node="input_validator")
        
    # Resume graph execution in the background
    canonical_path = state.get("dataset_path")
    original_filename = state.get("original_filename", "dataset.parquet")
    
    background_tasks.add_task(
        run_pipeline,
        run_id=run_id,
        canonical_path=canonical_path,
        input_format="parquet",
        user_prompt=state.get("user_prompt", ""),
        original_filename=original_filename,
        data_schema=state.get("dataset_schema"),
        clean_dataset_path=state.get("clean_dataset_path"),
    )
    
    return {
        "message": "Answers submitted and pipeline resume triggered successfully."
    }


@router.post("/pipeline/{run_id}/approve_plan", summary="Approve execution plan and resume cleaning pipeline")
async def api_approve_plan(
    run_id: str,
    background_tasks: BackgroundTasks,
):
    """Resume the pipeline from the plan-approval checkpoint."""
    config = {"configurable": {"thread_id": run_id}}
    
    async with get_checkpointer_manager().get() as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        snapshot = await graph.aget_state(config)
        
        if not snapshot or not snapshot.values:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
            
    # Resume graph execution in the background
    async def resume_graph():
        from app.core.websocket_manager import manager
        import time
        async with get_checkpointer_manager().get() as cp:
            gr = build_graph(checkpointer=cp, interrupt_before=[])
            try:
                async for event in gr.astream_events(None, config=config, version="v2"):
                    kind = event["event"]
                    name = event.get("name", "")
                    
                    if kind == "on_tool_start":
                        await manager.broadcast_to_run(run_id, {"event": "log", "log": {"timestamp": time.time(), "agent": name, "message": f"Calling tool '{name}'...", "level": "info"}})
                    elif kind == "on_tool_end":
                        await manager.broadcast_to_run(run_id, {"event": "log", "log": {"timestamp": time.time(), "agent": name, "message": f"Tool '{name}' completed successfully.", "level": "info"}})
                    elif kind == "on_tool_error":
                        err = event.get("data", {}).get("error", "Unknown error")
                        await manager.broadcast_to_run(run_id, {"event": "log", "log": {"timestamp": time.time(), "agent": name, "message": f"Tool '{name}' failed. Error: {err}", "level": "error"}})
                    elif kind == "on_chain_start":
                        if name in ["profiler", "semantic_profile", "input_validator", "planner", "supervisor", "deduplication", "null_handling", "type_casting", "validator", "report_agent"]:
                            await manager.broadcast_to_run(run_id, {"event": "log", "log": {"timestamp": time.time(), "agent": "system", "message": f"Starting step: {name}", "level": "info"}})
                    elif kind == "on_chain_error":
                        err = event.get("data", {}).get("error", "Unknown error")
                        if name != "LangGraph":
                            await manager.broadcast_to_run(run_id, {"event": "log", "log": {"timestamp": time.time(), "agent": "system", "message": f"Error in {name}: {err}", "level": "error"}})
                
                await manager.broadcast_to_run(run_id, {"event": "status_change", "status": "completed"})
            except Exception as e:
                logger.error(f"Pipeline resume error: {e}")
                await manager.broadcast_to_run(run_id, {"event": "status_change", "status": "failed"})
            
    background_tasks.add_task(resume_graph)
    
    return {
        "message": "Plan approved, pipeline execution resumed."
    }
