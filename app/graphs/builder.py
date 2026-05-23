"""Graph builder — assembles and compiles the LangGraph StateGraph.

Usage:
    async with get_checkpointer() as cp:
        graph = build_graph(checkpointer=cp)
        result = await graph.ainvoke(initial_state, config={"configurable": {"thread_id": job_id}})
"""
from langgraph.graph import END, StateGraph
from langgraph.checkpoint.base import BaseCheckpointSaver
from app.graphs.state import AgentState
from app.graphs.edges import supervisor_router
from app.graphs.nodes import (
    supervisor_node,
    profiler_node,
    cleaner_node,
    validator_node,
    transformer_node,
    reporter_node,
    error_node,
)
from app.core.config import get_settings

# Node name constants — import these elsewhere instead of using raw strings
SUPERVISOR = "supervisor_node"
PROFILER = "profiler_node"
CLEANER = "cleaner_node"
VALIDATOR = "validator_node"
TRANSFORMER = "transformer_node"
REPORTER = "reporter_node"
ERROR = "error_node"
END_REJECTED = "end_rejected"


def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    """Build and compile the multi-agent StateGraph.

    Args:
        checkpointer: Optional checkpoint saver for state persistence & HITL.

    Returns:
        A compiled CompiledStateGraph ready for invocation.
    """
    settings = get_settings()
    builder = StateGraph(AgentState)

    # ── Register nodes ──
    builder.add_node(SUPERVISOR, supervisor_node)
    builder.add_node(PROFILER, profiler_node)
    builder.add_node(CLEANER, cleaner_node)
    builder.add_node(VALIDATOR, validator_node)
    builder.add_node(TRANSFORMER, transformer_node)
    builder.add_node(REPORTER, reporter_node)
    builder.add_node(ERROR, error_node)

    # END_REJECTED is a terminal state (no-op node)
    builder.add_node(END_REJECTED, lambda state: state)

    # ── Entry point ──
    builder.set_entry_point(SUPERVISOR)

    # ── Supervisor routes to worker agents ──
    builder.add_conditional_edges(
        SUPERVISOR,
        supervisor_router,
        {
            PROFILER: PROFILER,
            CLEANER: CLEANER,
            VALIDATOR: VALIDATOR,
            TRANSFORMER: TRANSFORMER,
            REPORTER: REPORTER,
            END: END,
        },
    )

    # ── Worker agents return to supervisor after completion ──
    for worker in [PROFILER, CLEANER, VALIDATOR, TRANSFORMER, REPORTER]:
        builder.add_edge(worker, SUPERVISOR)

    # ── Error + rejected terminal edges ──
    builder.add_edge(ERROR, END)
    builder.add_edge(END_REJECTED, END)

    return builder.compile(
        checkpointer=checkpointer,
        # interrupt_before is handled inside nodes via interrupt() for finer control
        # but you can also use interrupt_before=[CLEANER, TRANSFORMER] here
    )
