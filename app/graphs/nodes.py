"""Node functions for the LangGraph pipeline."""
import logging
from typing import Any
from app.graphs.states.global_state import GlobalState, StatisticalProfile
from app.agents.input_validator.agent import InputValidatorAgent
from app.agents.semantic_analyzer.profiler_agent import SemanticProfilerAgent
from app.tools.data.eda import perform_eda

logger = logging.getLogger(__name__)

# Data profiling node (gọi function để thực hiện EDA trên dataset đã upload và lưu kết quả vào state)
async def profiler_node(state: GlobalState) -> dict[str, Any]:
    """Run statistical EDA on the uploaded dataset.

    Reads ``dataset_path`` from state, calls ``perform_eda``, and writes
    the result into ``data_profile``.
    """

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
    """Skeletal Deduplication Worker."""
    logger.info("dedup_agent_node: Executing dataset deduplication checks...")
    return {
        "current_step": "deduplication",
        "completed_steps": "deduplication",
    }

# Null Handling Worker stub node
async def null_agent_node(state: GlobalState) -> dict[str, Any]:
    """Skeletal Null Handling Worker."""
    logger.info("null_agent_node: Imputing missing values in dataset...")
    return {
        "current_step": "null_handling",
        "completed_steps": "null_handling",
    }

# Type Casting Worker stub node
async def type_agent_node(state: GlobalState) -> dict[str, Any]:
    """Skeletal Type Casting Worker."""
    logger.info("type_agent_node: Applying strict type cast constraints...")
    return {
        "current_step": "type_casting",
        "completed_steps": "type_casting",
    }

# Self-Correction Validator node
async def validator_node(state: GlobalState) -> dict[str, Any]:
    """Skeletal Validator Node — verifies worker outputs and processes retry counts."""
    current_idx = state.get("current_task_idx", 0)
    task_list = state.get("task_list", [])
    active_task = task_list[current_idx] if current_idx < len(task_list) else "unknown"
    
    logger.info(f"validator_node: Validating outputs of step '{active_task}'... PASS")
    
    # In skeletal phase, we always transition to the next step
    return {
        "current_task_idx": current_idx + 1,
        "retry_count": 0,
        "current_step": "validation",
        "completed_steps": "validation",
    }

# Final Report Generator node
async def report_agent_node(state: GlobalState) -> dict[str, Any]:
    """Skeletal Report Node — aggregates execution outcomes."""
    logger.info("report_agent_node: Summarizing transformations and token metrics...")
    return {
        "current_step": "reporting",
        "completed_steps": "reporting",
    }

