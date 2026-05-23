"""Pydantic schemas for agent inputs and outputs."""
from typing import Any
from pydantic import BaseModel, Field


class AgentInput(BaseModel):
    """Standard input passed into every agent."""
    job_id: str
    file_path: str
    rules: dict[str, Any] = Field(default_factory=dict)
    human_feedback: str = Field(default="", description="Feedback from HITL step")


class AgentOutput(BaseModel):
    """Standard output returned by every agent."""
    agent_name: str
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    next_agent: str | None = Field(
        default=None,
        description="If set, supervisor will route to this agent next",
    )
