"""Graph builder — assembles and compiles the LangGraph StateGraph."""

import logging
from typing import Any, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph

from app.graphs.nodes import (
    dedup_agent_node,
    input_validator_node,
    null_agent_node,
    planner_node,
    profiler_node,
    report_agent_node,
    semantic_profile_node,
    type_agent_node,
    validator_node,
)
from app.graphs.states.global_state import GlobalState

logger = logging.getLogger(__name__)


def route_to_current_task(state: GlobalState) -> str:
    """Route to the current worker task, or to the report when all tasks are done."""
    current_idx_val = state.get("current_task_idx")
    current_idx = current_idx_val if current_idx_val is not None else 0
    task_list = state.get("task_list") or []

    if current_idx < len(task_list):
        next_task = task_list[current_idx]
        # Map task keys to node names
        if next_task in ["deduplication", "null_handling", "type_casting"]:
            return next_task
        logger.warning(
            "route_to_current_task: Unrecognized task '%s'. Falling back to report.",
            next_task,
        )

    return "report_agent"


def route_from_input_validator(state: GlobalState) -> str:
    """Determine whether to proceed to planning or end the run to await human answers."""
    val_result = state.get("input_validation_result")
    if not val_result:
        return "planner"

    # Extract status safely (could be a dict or a Pydantic object)
    status = (
        val_result.get("status")
        if isinstance(val_result, dict)
        else getattr(val_result, "status", None)
    )
    if status == "needs_clarification":
        clarifications = (
            val_result.get("clarifications")
            if isinstance(val_result, dict)
            else getattr(val_result, "clarifications", None)
        )
        if clarifications:
            # Convert to dict if it is a Pydantic model
            if hasattr(clarifications, "model_dump"):
                clar_dict = clarifications.model_dump()
            elif hasattr(clarifications, "dict"):
                clar_dict = clarifications.dict()
            else:
                clar_dict = clarifications

            has_unanswered = False
            for cat in ["null", "duplicate", "typecast"]:
                cat_data = clar_dict.get(cat) if clar_dict else None
                if cat_data:
                    for q_key, q in cat_data.items():
                        if q and q.get("answer") is None:
                            has_unanswered = True
                            break
            if has_unanswered:
                logger.info(
                    "route_from_input_validator: Clarifications required, stopping run."
                )
                return "end"

    return "planner"


def route_from_validator(state: GlobalState) -> str:
    """Route after Pandera validation based on retry/replan decision."""
    next_node = state.get("next_node")
    if next_node == "planner":
        return "planner"
    return route_to_current_task(state)


class GraphBuilder:
    """Assembles the multi-agent ETL pipeline graph."""

    def build(self, checkpointer: BaseCheckpointSaver[Any] | None = None) -> Any:  # noqa: ANN401
        """Compile and return the StateGraph with stubs and HILT interrupts.

        Flow::

            START --> profiler --> semantic_profile --> input_validator --> planner
                  --> worker --> validator --> next worker/report
                  --> report_agent --> END
        """
        builder = StateGraph(cast(Any, GlobalState))

        # Register nodes
        builder.add_node("profiler", profiler_node)
        builder.add_node("semantic_profile", semantic_profile_node)
        builder.add_node("input_validator", input_validator_node)
        builder.add_node("planner", planner_node)
        builder.add_node("deduplication", dedup_agent_node)
        builder.add_node("null_handling", null_agent_node)
        builder.add_node("type_casting", type_agent_node)
        builder.add_node("validator", validator_node)
        builder.add_node("report_agent", report_agent_node)

        # Edges
        builder.set_entry_point("profiler")
        builder.add_edge("profiler", "semantic_profile")
        builder.add_edge("semantic_profile", "input_validator")

        # Route input_validator conditionally to either planner or END
        builder.add_conditional_edges(
            "input_validator", route_from_input_validator, {"planner": "planner", "end": END}
        )
        # Route directly from planner to the first active worker task.
        builder.add_conditional_edges(
            "planner",
            route_to_current_task,
            {
                "deduplication": "deduplication",
                "null_handling": "null_handling",
                "type_casting": "type_casting",
                "report_agent": "report_agent",
            },
        )

        # Worker edges to validator
        builder.add_edge("deduplication", "validator")
        builder.add_edge("null_handling", "validator")
        builder.add_edge("type_casting", "validator")

        # Validator feedback loop: pass/retry -> current worker/report, exhausted retries -> planner
        builder.add_conditional_edges(
            "validator",
            route_from_validator,
            {
                "deduplication": "deduplication",
                "null_handling": "null_handling",
                "type_casting": "type_casting",
                "report_agent": "report_agent",
                "planner": "planner",
            },
        )

        # Final endpoint
        builder.add_edge("report_agent", END)

        # Compile graph with HITL interrupt before worker execution and final report.
        return builder.compile(
            checkpointer=checkpointer,
            interrupt_before=["deduplication", "null_handling", "type_casting", "report_agent"],
        )


def build_graph(checkpointer: BaseCheckpointSaver[Any] | None = None) -> Any:  # noqa: ANN401
    """Convenience function to build and compile the graph."""
    return GraphBuilder().build(checkpointer=checkpointer)
