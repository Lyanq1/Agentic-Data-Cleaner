"""Graph builder — assembles and compiles the LangGraph ``StateGraph``."""
from langgraph.graph import END, StateGraph
from langgraph.checkpoint.base import BaseCheckpointSaver
from app.graphs.states.graph_state import GlobalState
from app.graphs.edges import EdgeRouter
from app.graphs.nodes import NodeRegistry, get_node_registry

class GraphBuilder:
    """Assembles and compiles the ``StateGraph``."""
    def __init__(self, node_registry: NodeRegistry | None = None) -> None:
        self._node_registry = node_registry or get_node_registry()

    def build(self, checkpointer: BaseCheckpointSaver | None = None):
        builder = StateGraph(GlobalState)
        nodes = self._node_registry.as_dict()

        # Register nodes
        for name, fn in nodes.items():
            builder.add_node(name, fn)

        # Entry point 
        builder.set_entry_point("template_node")

        # Routing
        builder.add_conditional_edges(
            "template_node",
            EdgeRouter.template_router,
            {
                END: END,
                # Add other nodes here if template_node returns them
            },
        )

        return builder.compile(checkpointer=checkpointer)

_graph_builder: GraphBuilder | None = None

def get_graph_builder(node_registry: NodeRegistry | None = None) -> GraphBuilder:
    """Return a ``GraphBuilder`` instance."""
    global _graph_builder
    if node_registry is not None:
        return GraphBuilder(node_registry=node_registry)
    if _graph_builder is None:
        _graph_builder = GraphBuilder()
    return _graph_builder
