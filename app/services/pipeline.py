"""Pipeline service — orchestrates the LangGraph execution."""
import logging
from pathlib import Path
from typing import Any

from app.graphs.graph import build_graph
from app.graphs.checkpointer import get_checkpointer_manager
from app.graphs.states.global_state import GlobalState

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
    clean_dataset_path: str | None = None,
    pipeline_mode: str | None = None,
) -> dict[str, Any]:
    """Run the profiler → input_validator pipeline on a canonical Parquet dataset.

    Args:
        run_id: Unique identifier for this pipeline run.
        canonical_path: Path to the canonical Parquet file (output of ingestion).
        input_format: Original file format before conversion (csv/excel/json).
        user_prompt: Optional user instruction for the cleaning task.
        original_filename: Original uploaded filename for reference.
        data_schema: Optional dataset schema dict.
        clean_dataset_path: Optional ground truth dataset path.
        pipeline_mode: Mode of execution (e.g. 'benchmark').

    Returns:
        Dict with run_id and the final state snapshot.
    """
    initial_state = {
        "messages": [],
        "dataset_path": canonical_path,
        "clean_dataset_path": clean_dataset_path,
        "ground_truth_path": clean_dataset_path,
        "user_prompt": user_prompt,
        "project_id": run_id,
        "session_id": Path(canonical_path).stem,
        "original_filename": original_filename,
        "dataset_schema": data_schema,
        "pipeline_mode": pipeline_mode,
    }

    config = {"configurable": {"thread_id": run_id}}

    async with get_checkpointer_manager().get() as checkpointer:
        graph = build_graph(checkpointer=checkpointer)

        logger.info(f"Pipeline started — run_id={run_id}, file={original_filename}, mode={pipeline_mode}")
        
        from app.core.websocket_manager import manager
        import asyncio
        import time
        
        # Give frontend a split second to connect to WebSocket before emitting
        await asyncio.sleep(0.5)

        try:
            async for event in graph.astream_events(initial_state, config=config, version="v2"):
                kind = event["event"]
                name = event.get("name", "")
                
                # Filter and broadcast tool/function events
                if kind == "on_tool_start":
                    await manager.broadcast_to_run(run_id, {
                        "event": "log",
                        "log": {
                            "timestamp": time.time(),
                            "agent": name,
                            "message": f"Calling tool '{name}'...",
                            "level": "info"
                        }
                    })
                elif kind == "on_tool_end":
                    await manager.broadcast_to_run(run_id, {
                        "event": "log",
                        "log": {
                            "timestamp": time.time(),
                            "agent": name,
                            "message": f"Tool '{name}' completed successfully.",
                            "level": "info"
                        }
                    })
                elif kind == "on_tool_error":
                    err = event.get("data", {}).get("error", "Unknown error")
                    await manager.broadcast_to_run(run_id, {
                        "event": "log",
                        "log": {
                            "timestamp": time.time(),
                            "agent": name,
                            "message": f"Tool '{name}' failed. Error: {err}",
                            "level": "error"
                        }
                    })
                elif kind == "on_chain_start":
                    if name in ["profiler", "semantic_profile", "input_validator", "planner", "supervisor", "deduplication", "null_handling", "type_casting", "validator", "report_agent"]:
                        await manager.broadcast_to_run(run_id, {
                            "event": "log",
                            "log": {
                                "timestamp": time.time(),
                                "agent": "system",
                                "message": f"Starting step: {name}",
                                "level": "info"
                            }
                        })
                elif kind == "on_chain_error":
                    err = event.get("data", {}).get("error", "Unknown error")
                    if name != "LangGraph": # avoid root error spam
                        await manager.broadcast_to_run(run_id, {
                            "event": "log",
                            "log": {
                                "timestamp": time.time(),
                                "agent": "system",
                                "message": f"Error in {name}: {err}",
                                "level": "error"
                            }
                        })
                        
        except Exception as e:
            logger.error(f"Pipeline execution error: {e}")
            await manager.broadcast_to_run(run_id, {
                "event": "status_change",
                "status": "failed"
            })

        logger.info(f"Pipeline finished — run_id={run_id}")
        
        snapshot = await graph.aget_state(config)
        final_state = snapshot.values if snapshot else initial_state

        # Check if the graph has paused at an interrupt (meaning execution is not fully completed yet)
        is_interrupted = bool(snapshot and snapshot.next)
        if not is_interrupted:
            await manager.broadcast_to_run(run_id, {
                "event": "status_change",
                "status": "completed"
            })
        else:
            await manager.broadcast_to_run(run_id, {
                "event": "status_change",
                "status": "paused"
            })

    raw_profile = final_state.get("statistical_profile")
    formatted_profile = _format_profile_for_frontend(raw_profile)

    return {
        "run_id": run_id,
        "original_filename": original_filename,
        "input_format": input_format,
        "canonical_path": canonical_path,
        "data_profile": formatted_profile,
        "semantic_profile": final_state.get("semantic_profile"),
        "dataset_schema": final_state.get("dataset_schema"),
        "input_validation_result": final_state.get("input_validation_result"),
        "execution_plan": final_state.get("execution_plan").model_dump() if final_state.get("execution_plan") and hasattr(final_state.get("execution_plan"), "model_dump") else final_state.get("execution_plan"),
        "completed_steps": final_state.get("completed_steps", []),
        "f1_metrics": final_state.get("f1_metrics"),
        "token_metrics": final_state.get("token_metrics"),
        "pipeline_mode": final_state.get("pipeline_mode"),
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
        "original_filename": state.get("original_filename"),
        "dataset_path": state.get("dataset_path"),
        "physical_dataframe_path": state.get("physical_dataframe_path"),
        "dataset_schema": state.get("dataset_schema"),
        "user_prompt": state.get("user_prompt"),
        # "statistical_profile": raw_profile,
        "data_profile": formatted_profile,
        "semantic_profile": state.get("semantic_profile"),
        "input_validation_result": state.get("input_validation_result"),
        "worker_states": state.get("worker_states"),
        "validation_results": state.get("validation_results", []),
        "agent_logs": state.get("agent_logs", {}),
        "deduplication_result": state.get("deduplication_result"),
        "current_dataset_version": state.get("current_dataset_version"),
        "hitl_status": state.get("hitl_status"),
        "hitl_checkpoint": state.get("hitl_checkpoint"),
        "execution_plan": state.get("execution_plan").model_dump() if state.get("execution_plan") and hasattr(state.get("execution_plan"), "model_dump") else state.get("execution_plan"),
        "task_list": state.get("task_list", []),
        "current_task_idx": state.get("current_task_idx", 0),
        "retry_count": state.get("retry_count", 0),
        "current_step": state.get("current_step"),
        "completed_steps": state.get("completed_steps", []),
        "errors": state.get("global_errors", []),
        "f1_metrics": state.get("f1_metrics"),
        "token_metrics": state.get("token_metrics"),
        "pipeline_mode": state.get("pipeline_mode"),
        "next_node": snapshot.next,  # which node would run next (empty if done)
    }



