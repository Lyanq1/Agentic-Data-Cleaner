"""Graph builder — assembles and compiles the LangGraph StateGraph."""
from langgraph.graph import END, StateGraph
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.graphs.states.graph_state import GlobalState
from app.graphs.nodes import profiler_node, input_validator_node


class GraphBuilder:
    """Assembles the profiler --> input_validator pipeline."""

    def build(self, checkpointer: BaseCheckpointSaver | None = None):
        """Compile and return the StateGraph.

        Flow::

            START --> profiler --> input_validator --> END (tạm thời chỉ có 2 node)
        """
        builder = StateGraph(GlobalState)

        # Register nodes
        builder.add_node("profiler", profiler_node)
        builder.add_node("input_validator", input_validator_node)

        # Edges
        builder.set_entry_point("profiler")
        builder.add_edge("profiler", "input_validator")
        builder.add_edge("input_validator", END)

        return builder.compile(checkpointer=checkpointer)

def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    """Convenience function to build and compile the graph."""
    return GraphBuilder().build(checkpointer=checkpointer)
