"""Conditional edge functions for routing.

Currently unused — the initial pipeline (profiler → input_validator) is linear.
Add routing functions here when branching logic is needed.
"""
from langgraph.graph import END
from app.graphs.states.global_state import GlobalState


def route_by_next_node(state: GlobalState) -> str:
    """Generic router: read ``next_node`` from state and route accordingly."""
    next_node = state.get("next_node")
    if next_node == "end" or not next_node:
        return END
    return next_node
