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
    """Determine the next worker task (deduplication, null_handling, or type_casting)
    to execute based on current_task_idx, or route to report_agent when finished.
    """
    current_idx_val = state.get("current_task_idx")
    current_idx = current_idx_val if current_idx_val is not None else 0
    task_list = state.get("task_list") or []

    if current_idx < len(task_list):
        next_task = task_list[current_idx]
        # Route to worker node based on task name
        if next_task == "deduplication":
            return "deduplication"
        elif next_task == "null_handling":
            return "null_handling"
        elif next_task == "type_casting":
            return "type_casting"
            
        logger.warning(
            "route_to_current_task: Unrecognized task '%s'. Falling back to report_agent.",
            next_task,
        )

    return "report_agent"


def route_from_validator(state: GlobalState) -> str:
    """Route after validator node execution.
    
    Flow:
      - If validation failed and requires replan: routes to 'planner'.
      - If validation failed and retrying: routes back to the current worker (dedup, typecast, or null).
      - If validation passed: moves to the next worker or 'report_agent'.
    """
    next_node = state.get("next_node")
    if next_node == "planner":
        return "planner"
        
    return route_to_current_task(state)


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



class GraphBuilder:
    """Assembles the multi-agent ETL pipeline graph."""

    def build(
        self,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
        *,
        interrupt_before: list[str] | None = None,
    ) -> Any:  # noqa: ANN401
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

        # Compile graph with HITL interrupt before worker execution by default.
        # Approval resumes use an empty interrupt list so workers, validators, and
        # report generation can finish in one background run.
        if interrupt_before is None:
            interrupt_before = ["deduplication", "type_casting", "null_handling", "report_agent"]

        return builder.compile(
            checkpointer=checkpointer,
            interrupt_before=interrupt_before,
        )


def build_graph(
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    *,
    interrupt_before: list[str] | None = None,
) -> Any:  # noqa: ANN401
    """Convenience function to build and compile the graph."""
    return GraphBuilder().build(
        checkpointer=checkpointer,
        interrupt_before=interrupt_before,
    )
