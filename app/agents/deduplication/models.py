"""Local orchestration models for the hybrid deduplication agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.graphs.states.planning import TaskDetail
from app.graphs.states.profiler_state import StatisticalProfile
from app.graphs.states.profiles import SemanticProfile
from app.graphs.states.workers import DedupDecisionTrace, DeduplicationReviewCase


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
    fuzzy_enabled: bool = False


class DedupDecision(BaseModel):
    """Raw LLM output used to select a dedup strategy."""

    mode: Literal["exact_full_row", "exact_key"]
    key_columns: list[str] = Field(default_factory=list)
    column_roles: dict[str, str] = Field(default_factory=dict)
    ignore_columns: list[str] = Field(default_factory=list)
    confidence: float | None = None
    reasoning_summary: str = ""


class ValidatedDedupDecision(BaseModel):
    """Dedup decision after deterministic validation and fallback."""

    mode: Literal["exact_full_row", "exact_key"]
    key_columns: list[str] = Field(default_factory=list)
    column_roles: dict[str, str] = Field(default_factory=dict)
    ignore_columns: list[str] = Field(default_factory=list)
    decision_source: Literal["llm", "planner_fallback", "profile_fallback", "safe_default"]
    confidence: float | None = None
    reasoning_summary: str = ""
    validation_notes: list[str] = Field(default_factory=list)
    unresolved_collisions: list[dict[str, Any]] = Field(default_factory=list)

    def to_trace(self, *, context_hash: str) -> DedupDecisionTrace:
        """Project the validated decision into the persisted trace model."""

        return DedupDecisionTrace(
            decision_source=self.decision_source,
            column_roles=dict(self.column_roles),
            ignore_columns=list(self.ignore_columns),
            confidence=self.confidence,
            reasoning_summary=self.reasoning_summary,
            validation_notes=list(self.validation_notes),
            context_hash=context_hash,
        )


class FuzzyCandidate(BaseModel):
    """A candidate pair surfaced by fuzzy blocking."""

    row_index_a: int
    row_index_b: int
    field: str
    similarity_score: float
    blocking_key: str
    candidate_type: Literal["company_name", "person_name", "address", "cross_script_name"]


class FuzzyCandidateSet(BaseModel):
    """In-memory summary of fuzzy candidates."""

    candidates: list[FuzzyCandidate] = Field(default_factory=list)
    oversized_buckets: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @property
    def total_count(self) -> int:
        return len(self.candidates)


class DeduplicationHitlDecision(BaseModel):
    case_id: str
    decision: Literal["merge", "do_not_merge"]
    reason: str | None = None


class DeduplicationHitlFeedback(BaseModel):
    decisions: list[DeduplicationHitlDecision] = Field(default_factory=list)


class AppliedHitlResult(BaseModel):
    deduped_df: Any
    applied_case_ids: list[str] = Field(default_factory=list)
    rejected_case_ids: list[str] = Field(default_factory=list)
    unknown_case_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    remaining_review_cases: list[DeduplicationReviewCase] = Field(default_factory=list)


@dataclass(slots=True)
class FuzzyBlockingConfig:
    """Static fuzzy blocking configuration for slice 2."""

    company_ngram_size: int = 3
    person_ngram_size: int = 2
    address_shingle_size: int = 2
    company_threshold: float = 0.5
    person_threshold: float = 0.4
    address_threshold: float = 0.6
    max_bucket_size: int = 500


@dataclass(slots=True)
class HitlConfig:
    max_review_cases: int = 50
