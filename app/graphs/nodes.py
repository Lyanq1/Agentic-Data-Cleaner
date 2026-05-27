"""Template node functions for the LangGraph pipeline."""
from collections.abc import Callable
from app.graphs.states.graph_state import GlobalState

class NodeRegistry:
    """Owns and caches all agent instances used as LangGraph nodes."""

    def __init__(self) -> None:
        # TODO: Initialize your agents here.
        pass

    async def template_node(self, state: GlobalState) -> dict:
        return {
            "next_node": "end",
        }

    def as_dict(self) -> dict[str, Callable]:
        """Return ``{node_name: callable}`` mapping for use by ``GraphBuilder``."""
        return {
            "template_node": self.template_node,
        }


# Module-level singleton

_node_registry: NodeRegistry | None = None

def get_node_registry() -> NodeRegistry:
    """Return the cached ``NodeRegistry`` singleton."""
    global _node_registry
    if _node_registry is None:
        _node_registry = NodeRegistry()
    return _node_registry
