"""AgentState — shared state TypedDict passed between all graph nodes."""
from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage


class AgentState(TypedDict):
    """Shared mutable state flowing through the LangGraph graph.

    All fields are optional (None) by default so that nodes can update
    only the fields they care about.

    HITL fields:
        human_approved: set to True after user approves via resume API.
        human_feedback: optional text injected from the resume payload.
        waiting_for_human: True when graph is paused at an interrupt node.
        hitl_node: name of the node where graph is currently paused.
    """
    # ── Core ──
    job_id: str
    file_path: str
    rules: dict
    # Messages (append-only via add_messages reducer)
    messages: Annotated[list[AnyMessage], add_messages]

    # ── Supervisor routing ──
    next_agent: str  # Which agent node to call next

    # ── Agent results ──
    profile_result: dict | None
    clean_result: dict | None
    validation_result: dict | None
    transform_result: dict | None
    report_result: dict | None

    # ── HITL ──
    human_approved: bool
    human_feedback: str
    waiting_for_human: bool
    hitl_node: str | None

    # ── Error handling ──
    error: str | None
    retry_count: int
