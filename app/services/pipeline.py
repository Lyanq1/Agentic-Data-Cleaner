"""Pipeline service — orchestrates the LangGraph execution."""
import uuid
import logging
from typing import Any

from app.graphs.graph import build_graph
from app.graphs.checkpointer import get_checkpointer_manager

logger = logging.getLogger(__name__)


def _format_profile_for_frontend(profile: Any) -> dict[str, Any] | None:
    if not profile:
        return None
    if hasattr(profile, "model_dump"):
        profile_dict = profile.model_dump()
    elif hasattr(profile, "dict"):
        profile_dict = profile.dict()
    elif isinstance(profile, dict):
        import copy
        profile_dict = copy.deepcopy(profile)
    else:
        return None

    columns_list = profile_dict.get("columns", [])
    columns_dict = {}
    for col in columns_list:
        col_name = col.get("column_name")
        if col_name:
            columns_dict[col_name] = col
    
    profile_dict["columns"] = columns_dict
    return profile_dict


async def run_pipeline(
    run_id: str,
    canonical_path: str,
    input_format: str,
    user_prompt: str = "",
    original_filename: str = "",
    data_schema: dict | None = None,
) -> dict[str, Any]:
    """Run the profiler → input_validator pipeline on a canonical Parquet dataset.

    Args:
        run_id: Unique identifier for this pipeline run.
        canonical_path: Path to the canonical Parquet file (output of ingestion).
        input_format: Original file format before conversion (csv/excel/json).
        user_prompt: Optional user instruction for the cleaning task.
        original_filename: Original uploaded filename for reference.

    Returns:
        Dict with run_id and the final state snapshot.
    """
    initial_state = {
        "messages": [],
        "dataset_path": canonical_path,
        "user_prompt": user_prompt,
        "project_id": run_id,
        "dataset_schema": data_schema,
    }

    config = {"configurable": {"thread_id": run_id}}

    async with get_checkpointer_manager().get() as checkpointer:
        graph = build_graph(checkpointer=checkpointer)

        logger.info(f"Pipeline started — run_id={run_id}, file={original_filename}")
        final_state = await graph.ainvoke(initial_state, config=config)
        logger.info(f"Pipeline finished — run_id={run_id}")

    raw_profile = final_state.get("statistical_profile")
    formatted_profile = _format_profile_for_frontend(raw_profile)

    return {
        "run_id": run_id,
        "original_filename": original_filename,
        "input_format": input_format,
        "canonical_path": canonical_path,
        "statistical_profile": raw_profile,
        "data_profile": formatted_profile,
        "semantic_profile": final_state.get("semantic_profile"),
        "dataset_schema": final_state.get("dataset_schema"),
        "statistical_profile": final_state.get("statistical_profile"),
        "input_validation_result": final_state.get("input_validation_result"),
        "completed_steps": final_state.get("completed_steps", []),
    }


async def get_pipeline_state(run_id: str) -> dict[str, Any] | None:
    """Retrieve the current state of a pipeline run from the checkpointer.

    Args:
        run_id: The run/thread ID to look up.

    Returns:
        Dict with current state, or None if not found.
    """
    config = {"configurable": {"thread_id": run_id}}

    async with get_checkpointer_manager().get() as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        snapshot = await graph.aget_state(config)

    if not snapshot or not snapshot.values:
        return None

    state = snapshot.values
    raw_profile = state.get("statistical_profile")
    formatted_profile = _format_profile_for_frontend(raw_profile)

    return {
        "run_id": run_id,
        "dataset_path": state.get("dataset_path"),
        "dataset_schema": state.get("dataset_schema"),
        "user_prompt": state.get("user_prompt"),
        "statistical_profile": raw_profile,
        "data_profile": formatted_profile,
        "semantic_profile": state.get("semantic_profile"),
        "input_validation_result": state.get("input_validation_result"),
        "current_step": state.get("current_step"),
        "completed_steps": state.get("completed_steps", []),
        "errors": state.get("global_errors", []),
        "next_node": snapshot.next,  # which node would run next (empty if done)
    }
