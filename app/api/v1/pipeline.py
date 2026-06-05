"""Pipeline API — upload dataset, run pipeline, check state."""
import uuid
import logging

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from pydantic import BaseModel
from langchain_core.messages import HumanMessage

from app.exceptions.ingestion_exceptions import IngestionError
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
        async with get_checkpointer_manager().get() as cp:
            gr = build_graph(checkpointer=cp)
            # Passing None as inputs resumes from the last checkpoint
            await gr.ainvoke(None, config=config)
            
    background_tasks.add_task(resume_graph)
    
    return {
        "message": "Plan approved, pipeline execution resumed."
    }
