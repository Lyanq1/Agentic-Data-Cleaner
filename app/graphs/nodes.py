"""Template node functions for the LangGraph pipeline."""
from collections.abc import Callable
from app.graphs.states.graph_state import GlobalState

class NodeRegistry:
    """Owns and caches all agent instances used as LangGraph nodes."""

    def __init__(self) -> None:
        # TODO: Initialize your agents here.
        pass

    async def template_node(self, state: GlobalState) -> dict:
        """A minimal template for a LangGraph node.
        
        Args:
            state: The current global state.
            
        Returns:
            A dictionary containing partial updates to the state.
        """
        
        # TODO: Implement your agent's logic here.
        # Example: Call an LLM, run a tool, etc.
        
        # Return state updates
        return {
            "next_node": "end",  # Set the next node to route to
            # "messages": [...],
        }

    def as_dict(self) -> dict[str, Callable]:
        """Return ``{node_name: callable}`` mapping for use by ``GraphBuilder``."""
        return {
            "template_node": self.template_node,
        }


# ── Module-level singleton ────────────────────────────────────────────────────

_node_registry: NodeRegistry | None = None

def get_node_registry() -> NodeRegistry:
    """Return the cached ``NodeRegistry`` singleton."""
    global _node_registry
    if _node_registry is None:
        _node_registry = NodeRegistry()
    return _node_registry
