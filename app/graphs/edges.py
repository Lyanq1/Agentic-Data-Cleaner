"""Conditional edge functions for routing, grouped in ``EdgeRouter``."""
from langgraph.graph import END
from app.graphs.states.graph_state import GlobalState

class EdgeRouter:
    """Namespace for all LangGraph conditional edge routing functions."""

    @staticmethod
    def template_router(state: GlobalState) -> str:
        """Route to the next node based on the state.
        
        Args:
            state: The current global state.
            
        Returns:
            The name of the next node to execute, or END.
        """
        next_node = state.get("next_node")
        
        if next_node == "end" or not next_node:
            return END
            
        return next_node
