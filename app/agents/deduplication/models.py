"""Local orchestration models for the hybrid deduplication agent."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.graphs.states.planning import TaskDetail
from app.graphs.states.profiler_state import StatisticalProfile
from app.graphs.states.profiles import SemanticProfile
from app.graphs.states.workers import DedupDecisionTrace


class DeduplicationAgentInput(BaseModel):
    """Runtime input contract derived from GlobalState for the dedup agent."""

    project_id: str | None = None
    dataset_path: str
    dataset_schema: dict[str, Any] | None = None
    user_prompt: str | None = None
    statistical_profile: StatisticalProfile | None = None
    semantic_profile: SemanticProfile | None = None
    planner_task: TaskDetail | None = None
    retry_count: int = 0
    hitl_feedback: str | None = None


class DedupDecision(BaseModel):
    """Raw LLM output used to select a dedup strategy."""

    mode: Literal["exact_full_row", "exact_key", "review_needed"]
    key_columns: list[str] = Field(default_factory=list)
    ignore_columns: list[str] = Field(default_factory=list)
    confidence: float | None = None
    reasoning_summary: str = ""


class ValidatedDedupDecision(BaseModel):
    """Dedup decision after deterministic validation and fallback."""

    mode: Literal["exact_full_row", "exact_key", "review_needed"]
    key_columns: list[str] = Field(default_factory=list)
    ignore_columns: list[str] = Field(default_factory=list)
    decision_source: Literal["llm", "planner_fallback", "profile_fallback", "safe_default"]
    confidence: float | None = None
    reasoning_summary: str = ""
    validation_notes: list[str] = Field(default_factory=list)

    def to_trace(self, *, context_hash: str) -> DedupDecisionTrace:
        """Project the validated decision into the persisted trace model."""

        return DedupDecisionTrace(
            decision_source=self.decision_source,
            ignore_columns=list(self.ignore_columns),
            confidence=self.confidence,
            reasoning_summary=self.reasoning_summary,
            validation_notes=list(self.validation_notes),
            context_hash=context_hash,
        )
