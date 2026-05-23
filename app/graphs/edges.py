"""Conditional edge functions for supervisor routing.

Each function receives the current AgentState and returns the name
of the next node to execute (or END to finish the graph).
"""
from langgraph.graph import END
from app.graphs.state import AgentState

# Sentinel value used when the graph should terminate
FINISH = END


def supervisor_router(state: AgentState) -> str:
    """Route to the next agent based on supervisor's decision.

    The supervisor node sets `state["next_agent"]` to one of:
    - "profiler_node"
    - "cleaner_node"
    - "validator_node"
    - "transformer_node"
    - "reporter_node"
    - END (finished)
    """
    next_agent = state.get("next_agent", END)
    if next_agent == FINISH or not next_agent:
        return END
    return next_agent


def hitl_router(state: AgentState) -> str:
    """After an interrupt, route based on human approval.

    Returns:
        "supervisor_node" if approved, "end_rejected" if rejected.
    """
    if state.get("human_approved", False):
        return "supervisor_node"
    return "end_rejected"


def error_router(state: AgentState) -> str:
    """If an unrecoverable error occurred, route to error handler."""
    if state.get("error") and state.get("retry_count", 0) >= 3:
        return "error_node"
    return "supervisor_node"
