"""Graph builder — assembles and compiles the LangGraph StateGraph."""
import logging
from langgraph.graph import END, StateGraph
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.graphs.states.global_state import GlobalState
from app.graphs.nodes import (
    profiler_node,
    semantic_profile_node,
    input_validator_node,
    planner_node,
    supervisor_node,
    dedup_agent_node,
    null_agent_node,
    type_agent_node,
    validator_node,
    report_agent_node,
)

logger = logging.getLogger(__name__)


def route_from_supervisor(state: GlobalState):
    """Determine the next step in the DAG from the supervisor state."""
    current_idx = state.get("current_task_idx", 0)
    task_list = state.get("task_list", [])
    
    if current_idx < len(task_list):
        next_task = task_list[current_idx]
        # Map task keys to node names
        if next_task in ["deduplication", "null_handling", "type_casting"]:
            return next_task
        logger.warning(f"route_from_supervisor: Unrecognized task '{next_task}'. Falling back to supervisor check.")
        
    return "report_agent"


def route_from_input_validator(state: GlobalState):
    """Determine whether to proceed to planning or end the run to await human answers."""
    val_result = state.get("input_validation_result")
    if not val_result:
        return "planner"
    
    # Extract status safely (could be a dict or a Pydantic object)
    status = val_result.get("status") if isinstance(val_result, dict) else getattr(val_result, "status", None)
    if status == "needs_clarification":
        clarifications = val_result.get("clarifications") if isinstance(val_result, dict) else getattr(val_result, "clarifications", None)
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
                logger.info("route_from_input_validator: Clarifications required, stopping run to await user responses.")
                return "end"
                
    return "planner"


class GraphBuilder:
    """Assembles the multi-agent ETL pipeline graph."""

    def build(self, checkpointer: BaseCheckpointSaver | None = None):
        """Compile and return the StateGraph with stubs and HILT interrupts.

        Flow::

            START --> profiler --> semantic_profile --> input_validator --> planner
                  --> supervisor (Dynamic routing loop)
                      --> deduplication --> validator --> supervisor
                      --> null_handling --> validator --> supervisor
                      --> type_casting  --> validator --> supervisor
                  --> report_agent --> END
        """
        builder = StateGraph(GlobalState)

        # Register nodes
        builder.add_node("profiler", profiler_node)
        builder.add_node("semantic_profile", semantic_profile_node)
        builder.add_node("input_validator", input_validator_node)
        builder.add_node("planner", planner_node)
        builder.add_node("supervisor", supervisor_node)
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
            "input_validator",
            route_from_input_validator,
            {
                "planner": "planner",
                "end": END
            }
        )
        builder.add_edge("planner", "supervisor")

        # Dynamic routing loop from supervisor
        builder.add_conditional_edges(
            "supervisor",
            route_from_supervisor,
            {
                "deduplication": "deduplication",
                "null_handling": "null_handling",
                "type_casting": "type_casting",
                "report_agent": "report_agent",
            }
        )

        # Worker edges to validator
        builder.add_edge("deduplication", "validator")
        builder.add_edge("null_handling", "validator")
        builder.add_edge("type_casting", "validator")
        
        # Validator feedback loop to supervisor
        builder.add_edge("validator", "supervisor")
        
        # Final endpoint
        builder.add_edge("report_agent", END)

        # Compile graph with HITL interrupt before Report Agent only (no supervisor interrupt)
        return builder.compile(
            checkpointer=checkpointer,
            interrupt_before=["report_agent"]
        )


def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    """Convenience function to build and compile the graph."""
    return GraphBuilder().build(checkpointer=checkpointer)
