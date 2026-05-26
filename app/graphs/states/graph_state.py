"""State templates for the LangGraph pipeline."""
from typing import Annotated, Any
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage


class GlobalState(TypedDict):
    """Shared mutable state flowing through the entire LangGraph graph.
    
    This state is accessible to all agents. Add fields here that need to be
    shared globally across the pipeline.
    """
    # ── Core routing & messages ──
    messages: Annotated[list[AnyMessage], add_messages]
    next_node: str | None  # Route to the next node

    # ── User configurable global fields ──
    # TODO: Add your global configuration fields here.
    # Examples:
    # project_id: str
    # shared_data: dict[str, Any]
    

class AgentState(TypedDict):
    """Template for individual agent state.
    
    This can be used if an agent runs as a sub-graph, or to define the specific
    keys an agent is allowed to return as a state update to the GlobalState.
    """
    # ── User configurable agent fields ──
    # TODO: Add your agent-specific fields here.
    # Examples:
    # agent_scratchpad: list[str]
    # local_result: dict[str, Any]
    pass
