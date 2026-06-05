"""Pipeline service — orchestrates the LangGraph execution."""
import copy
import uuid
import logging
from pathlib import Path
from typing import Any

from app.agents.deduplication.agent import DeduplicationAgent
from app.agents.roles import AgentRole
from app.graphs.graph import build_graph
from app.graphs.checkpointer import get_checkpointer_manager
from app.graphs.states.global_state import ExecutionPlan, TaskDetail, TaskDetailWrapper, PlanMetadata, GlobalConstraints, GlobalState

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
        "session_id": Path(canonical_path).stem,
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
        "data_profile": formatted_profile,
        "semantic_profile": final_state.get("semantic_profile"),
        "dataset_schema": final_state.get("dataset_schema"),
        "input_validation_result": final_state.get("input_validation_result"),
        "execution_plan": final_state.get("execution_plan").model_dump() if final_state.get("execution_plan") and hasattr(final_state.get("execution_plan"), "model_dump") else final_state.get("execution_plan"),
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
        "physical_dataframe_path": state.get("physical_dataframe_path"),
        "dataset_schema": state.get("dataset_schema"),
        "user_prompt": state.get("user_prompt"),
        # "statistical_profile": raw_profile,
        "data_profile": formatted_profile,
        "semantic_profile": state.get("semantic_profile"),
        "input_validation_result": state.get("input_validation_result"),
        "worker_states": state.get("worker_states"),
        "validation_results": state.get("validation_results", []),
        "deduplication_result": state.get("deduplication_result"),
        "current_dataset_version": state.get("current_dataset_version"),
        "execution_plan": state.get("execution_plan").model_dump() if state.get("execution_plan") and hasattr(state.get("execution_plan"), "model_dump") else state.get("execution_plan"),
        "current_step": state.get("current_step"),
        "completed_steps": state.get("completed_steps", []),
        "errors": state.get("global_errors", []),
        "next_node": snapshot.next,  # which node would run next (empty if done)
    }


async def get_pipeline_raw_state(run_id: str) -> GlobalState | None:
    """Retrieve the raw checkpointed state snapshot for a run."""
    config = {"configurable": {"thread_id": run_id}}

    async with get_checkpointer_manager().get() as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        snapshot = await graph.aget_state(config)

    if not snapshot or not snapshot.values:
        return None

    return snapshot.values  # type: ignore


def _inject_dedup_key_columns(state: GlobalState, key_columns: list[str]) -> GlobalState:
    """Inject requested key columns into the working execution plan for dedup."""
    if not key_columns:
        return state

    working_state = copy.deepcopy(state)
    existing_plan = working_state.get("execution_plan")
    if existing_plan:
        plan = ExecutionPlan.model_validate(existing_plan)
    else:
        plan = ExecutionPlan(
            metadata=PlanMetadata(
                plan_id="debug",
                plan_version=1,
                created_at="2026-06-06T00:00:00"
            ),
            global_constraints=GlobalConstraints(
                max_retries_per_task=3,
                preserve_columns=[]
            ),
            task_list=[],
            plan_summary="Debug dedup execution plan."
        )

    dedup_task = TaskDetail(
        task_id="deduplication",
        agent=AgentRole.DEDUP_AGENT,
        skip=False,
        columns=key_columns,
        strategy={"requested_via_debug_endpoint": True},
    )
    updated_tasks = [
        task
        for task in plan.task_list
        if task.work_order.task_id != "deduplication" and task.work_order.agent != AgentRole.DEDUP_AGENT
    ]
    updated_tasks.insert(0, TaskDetailWrapper(work_order=dedup_task))

    working_state["execution_plan"] = ExecutionPlan(
        metadata=plan.metadata,
        global_constraints=plan.global_constraints,
        task_list=updated_tasks,
        plan_summary=plan.plan_summary or "Debug dedup execution plan.",
    )
    return working_state


async def run_dedup_agent_for_run(
    run_id: str,
    key_columns: list[str] | None = None,
) -> dict[str, Any] | None:
    """Load a checkpointed state by run_id and execute the dedup agent directly."""
    raw_state = await get_pipeline_raw_state(run_id)
    if raw_state is None:
        return None

    requested_key_columns = key_columns or []
    dataset_schema = raw_state.get("dataset_schema") or {}
    missing_columns = [
        column for column in requested_key_columns if dataset_schema and column not in dataset_schema
    ]
    if missing_columns:
        raise ValueError(f"Unknown key columns: {missing_columns}")

    working_state = _inject_dedup_key_columns(raw_state, requested_key_columns)
    agent = DeduplicationAgent()
    updates = await agent.run(working_state)

    config = {"configurable": {"thread_id": run_id}}
    async with get_checkpointer_manager().get() as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        await graph.aupdate_state(config, updates, as_node="deduplication")

    persisted_state = await get_pipeline_state(run_id)
    return {
        "run_id": run_id,
        "requested_key_columns": requested_key_columns,
        "state": persisted_state,
    }
