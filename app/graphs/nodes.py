"""Node functions for the LangGraph pipeline."""
import logging
from typing import Any

from app.graphs.states.graph_state import GlobalState

logger = logging.getLogger(__name__)

# Data profiling node (gọi function để thực hiện EDA trên dataset đã upload và lưu kết quả vào state)
async def profiler_node(state: GlobalState) -> dict[str, Any]:
    """Run statistical EDA on the uploaded dataset.

    Reads ``dataset_path`` from state, calls ``perform_eda``, and writes
    the result into ``data_profile``.
    """
    from app.tools.data.eda import perform_eda

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
        "data_profile": profile,
        "current_step": "profiling",
        "completed_steps": "profiling",
    }

# Input validation node (gọi agent để phân tích data profile và đưa ra đánh giá về chất lượng dữ liệu)
async def input_validator_node(state: GlobalState) -> dict[str, Any]:
    """Invoke the InputValidatorAgent to analyze the EDA profile via LLM."""
    from app.agents.input_validator.agent import InputValidatorAgent

    agent = InputValidatorAgent()
    result = await agent.run(state)

    return {
        **result,
        "current_step": "input_validation",
        "completed_steps": "input_validation",
    }
