"""Node functions for the LangGraph pipeline."""
import logging
from datetime import datetime, timezone
from typing import Any
from app.agents.deduplication.agent import DeduplicationAgent
from app.graphs.states.global_state import GlobalState, StatisticalProfile
from app.agents.input_validator.agent import InputValidatorAgent
from app.agents.semantic_analyzer.profiler_agent import SemanticProfilerAgent
from app.graphs.states.global_state import GlobalState, StatisticalProfile, ValidationResultItem
from app.services.lineage_service import LineageService
from app.services.lineage_utils import resolve_lineage_session_id
from app.tools.data.eda import perform_eda
from app.validators import validate_current_task

logger = logging.getLogger(__name__)

# Data profiling node (gọi function để thực hiện EDA trên dataset đã upload và lưu kết quả vào state)
async def profiler_node(state: GlobalState) -> dict[str, Any]:
    """Run statistical EDA on the uploaded dataset.

    Reads ``dataset_path`` from state, calls ``perform_eda``, and writes
    the result into ``data_profile``.
    """
    if state.get("statistical_profile"):
        logger.info("profiler_node: Statistical profile already exists in state, skipping.")
        return {}

    dataset_path = state.get("dataset_path")
    if not dataset_path:
        logger.error("profiler_node: dataset_path is missing from state.")
        return {
            "global_errors": "profiler_node: dataset_path is missing from state.",
        }

    logger.info(f"profiler_node: profiling dataset at {dataset_path}")
    try:
        # perform_eda is a @tool — call .invoke() to get the dict result
        profile: dict = perform_eda.invoke({"file_path": dataset_path})
        validated_profile = StatisticalProfile.model_validate(profile)
    except Exception as e:
        logger.error(f"profiler_node: EDA failed — {e}")
        return {
            "global_errors": f"profiler_node: EDA failed — {e}",
        }

    logger.info(
        f"profiler_node: profiling complete — "
        f"{profile.get('total_rows', '?')} rows × {profile.get('total_columns', '?')} cols"
    )
    return {
        "statistical_profile": validated_profile,
        "current_step": "profiling",
        "completed_steps": "profiling",
    }

async def semantic_profile_node(state: GlobalState) -> dict[str, Any]:
    """Profile detailed semantic properties of the dataset columns by logical group."""
    if state.get("semantic_profile"):
        logger.info("semantic_profile_node: Semantic profile already exists in state, skipping.")
        return {}
    agent = SemanticProfilerAgent()
    return await agent.run(state)

# Input validation node (gọi agent để phân tích data profile và đưa ra đánh giá về chất lượng dữ liệu)
async def input_validator_node(state: GlobalState) -> dict[str, Any]:
    """Invoke the InputValidatorAgent to analyze the EDA profile via LLM."""

    agent = InputValidatorAgent()
    result = await agent.run(state)

    return {
        **result,
        "current_step": "input_validation",
        "completed_steps": "input_validation",
    }

# Planner node (Đề xuất kế hoạch làm sạch động)
async def planner_node(state: GlobalState) -> dict[str, Any]:
    """Invoke the PlannerAgent to generate the cleaning plan and task list."""
    logger.info("planner_node: Generating cleaning plan and DAG task list...")
    from app.agents.planner.agent import PlannerAgent
    
    agent = PlannerAgent()
    result = await agent.run(state)
    
    return {
        **result,
        "current_step": "planning",
        "completed_steps": "planning",
    }

# Supervisor node (Điều phối luồng chạy của các Worker)
async def supervisor_node(state: GlobalState) -> dict[str, Any]:
    """Skeletal Supervisor Node — increments indices and coordinates task steps."""
    current_idx = state.get("current_task_idx", 0)
    task_list = state.get("task_list", [])
    
    if current_idx < len(task_list):
        active_task = task_list[current_idx]
        logger.info(f"supervisor_node: Active task is '{active_task}' (index {current_idx}/{len(task_list)})")
    else:
        logger.info("supervisor_node: All tasks in DAG completed successfully.")
        
    return {
        "current_step": "supervisor",
        "completed_steps": "supervisor",
    }

# Deduplication Worker stub node
async def dedup_agent_node(state: GlobalState) -> dict[str, Any]:
    """Run the deterministic simple-case deduplication worker."""
    logger.info("dedup_agent_node: Executing dataset deduplication checks...")
    agent = DeduplicationAgent()
    result = await agent.run(state)

    return {
        **result,
        "current_step": "deduplication",
        "completed_steps": "deduplication",
    }

# Null Handling Worker stub node
async def null_agent_node(state: GlobalState) -> dict[str, Any]:
    """Skeletal Null Handling Worker."""
    logger.info("null_agent_node: Imputing missing values in dataset...")
    return _persist_passthrough_worker_version(state, "null_agent", "null_handling")

# Type Casting Worker stub node
async def type_agent_node(state: GlobalState) -> dict[str, Any]:
    """Skeletal Type Casting Worker."""
    logger.info("type_agent_node: Applying strict type cast constraints...")
    return _persist_passthrough_worker_version(state, "typecast_agent", "type_casting")


def _persist_passthrough_worker_version(
    state: GlobalState,
    agent_name: str,
    step_name: str,
) -> dict[str, Any]:
    """Worker stub contract: load latest lineage dataframe and save a new version.

    Real workers should replace the pass-through dataframe with their transformed
    dataframe, then keep the same append/version state update behavior.
    """
    base_update: dict[str, Any] = {
        "current_step": step_name,
        "completed_steps": step_name,
    }
    session_id = resolve_lineage_session_id(state)
    if not session_id:
        logger.warning("%s: lineage session id missing; skipping version append.", agent_name)
        return base_update

    try:
        dataframe = LineageService.get_latest_version(session_id)
        if dataframe.empty:
            logger.warning("%s: latest lineage dataframe is empty; skipping version append.", agent_name)
            return base_update

        new_version = LineageService.append_new_version(
            session_id=session_id,
            df=dataframe,
            agent_name=agent_name,
            description=f"Pass-through skeletal output for {step_name}.",
        )
    except Exception as exc:
        logger.error("%s: failed to persist lineage version: %s", agent_name, exc)
        return {
            **base_update,
            "global_errors": f"{agent_name}: failed to persist lineage version: {exc}",
        }

    return {
        **base_update,
        "dataset_version": str(new_version),
        "current_dataset_version": str(new_version),
    }

# Self-Correction Validator node
async def validator_node(state: GlobalState) -> dict[str, Any]:
    """Validate the active worker output with Pandera and update retry routing state."""
    current_idx = state.get("current_task_idx") or 0
    retry_count = state.get("retry_count") or 0
    outcome = validate_current_task(state)

    validation_item = ValidationResultItem(
        agent=outcome.agent,
        task_id=outcome.task_id,
        passed=outcome.passed,
        failed_rules=outcome.failed_rules,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    if outcome.passed:
        logger.info(
            "validator_node: task '%s' passed Pandera validation%s.",
            outcome.task_id,
            " (skipped)" if outcome.skipped else "",
        )
        return {
            "current_task_idx": current_idx + 1,
            "retry_count": 0,
            "last_validation_error": None,
            "failed_task_id": None,
            "replan_reason": None,
            "next_node": None,
            "validation_results": validation_item,
            "current_step": "validation",
            "completed_steps": "validation",
        }

    retry_count += 1
    max_retries = _max_retries_per_task(state)
    error_log = outcome.compact_error_log()

    if retry_count >= max_retries:
        logger.warning(
            "validator_node: task '%s' failed validation after %s/%s retries; routing to planner.",
            outcome.task_id,
            retry_count,
            max_retries,
        )
        return {
            "retry_count": retry_count,
            "last_validation_error": error_log,
            "failed_task_id": outcome.task_id,
            "replan_reason": f"Pandera validation failed after {retry_count} attempts.",
            "next_node": "planner",
            "validation_results": validation_item,
            "global_errors": error_log,
            "current_step": "validation_failed",
        }

    logger.warning(
        "validator_node: task '%s' failed validation; retry %s/%s.",
        outcome.task_id,
        retry_count,
        max_retries,
    )
    return {
        "retry_count": retry_count,
        "last_validation_error": error_log,
        "failed_task_id": outcome.task_id,
        "next_node": None,
        "validation_results": validation_item,
        "current_step": "validation_failed",
    }


def _max_retries_per_task(state: GlobalState) -> int:
    plan = state.get("execution_plan")
    if plan is None:
        return 3
    constraints = plan.get("global_constraints") if isinstance(plan, dict) else plan.global_constraints
    if constraints is None:
        return 3
    value = constraints.get("max_retries_per_task") if isinstance(constraints, dict) else constraints.max_retries_per_task
    return int(value or 3)

# Final Report Generator node
async def report_agent_node(state: GlobalState) -> dict[str, Any]:
    """Skeletal Report Node — aggregates execution outcomes."""
    logger.info("report_agent_node: Summarizing transformations and token metrics...")
    return {
        "current_step": "reporting",
        "completed_steps": "reporting",
    }

