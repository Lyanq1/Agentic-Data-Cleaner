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


class GraphBuilder:
    """Assembles the multi-agent ETL pipeline graph."""

    def build(self, checkpointer: BaseCheckpointSaver | None = None):
        """Compile and return the StateGraph with stubs and HILT interrupts.

        Flow::

            START --> profiler --> semantic_profile --> input_validator --> planner --> [HITL 1]
                  --> supervisor (Dynamic routing loop)
                      --> deduplication --> validator --> supervisor
                      --> null_handling --> validator --> supervisor
                      --> type_casting  --> validator --> supervisor
                  --> [HITL 2] --> report_agent --> END
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
        builder.add_edge("input_validator", "planner")
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

        # Compile graph with HITL interrupts before Supervisor (Checkpoint 1) and Report Agent (Checkpoint 2)
        return builder.compile(
            checkpointer=checkpointer,
            interrupt_before=["supervisor", "report_agent"]
        )


def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    """Convenience function to build and compile the graph."""
    return GraphBuilder().build(checkpointer=checkpointer)
