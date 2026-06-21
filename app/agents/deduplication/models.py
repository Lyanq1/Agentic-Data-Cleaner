"""Local orchestration models for the hybrid deduplication agent."""

from __future__ import annotations

from dataclasses import dataclass
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
    fuzzy_enabled: bool = False


class DedupDecision(BaseModel):
    """Raw LLM output used to select a dedup strategy."""

    mode: Literal["exact_full_row", "exact_key"]
    key_columns: list[str] = Field(default_factory=list)
    column_semantics: dict[str, dict[str, Any]] = Field(default_factory=dict)
    ignore_columns: list[str] = Field(default_factory=list)
    fuzzy_plan: dict[str, Any] | None = None
    confidence: float | None = None
    reasoning_summary: str = ""


class ColumnSemanticDescriptor(BaseModel):
    semantic_label: str = ""
    comparison_intent: str = ""
    normalization_intent: str = ""
    identifier_intent: str = ""
    blocking_intent: str = ""


class BlockKeySpec(BaseModel):
    columns: list[str] = Field(default_factory=list)
    transform: str = "normalized_prefix"
    required: bool = False


class EvidenceSpec(BaseModel):
    target_blocking_specs: list[str] = Field(default_factory=list)
    support_columns: list[str] = Field(default_factory=list)
    reject_columns: list[str] = Field(default_factory=list)
    minimum_support_matches: int = 0
    hard_reject_on_conflict: bool = True


class BlockingSpec(BaseModel):
    spec_id: str = ""
    target_columns: list[str] = Field(default_factory=list)
    semantic_label: str = ""
    comparison_intent: str = ""
    blocking_intent: str = ""
    strategy: str = "token_blocking"
    block_keys: list[BlockKeySpec] = Field(default_factory=list)
    sub_block_columns: list[str] = Field(default_factory=list)
    similarity_metric: str = "jaccard"
    similarity_threshold: float = 0.5
    max_bucket_size: int = 500
    oversized_bucket_strategy: str = "sub_block"


class FuzzyExecutionPlan(BaseModel):
    enabled: bool = False
    entity_scope: str | None = None
    blocking_specs: list[BlockingSpec] = Field(default_factory=list)
    evidence_specs: list[EvidenceSpec] = Field(default_factory=list)
    candidate_resolution_policy: str = "preview_only"
    notes: list[str] = Field(default_factory=list)


class ValidatedDedupDecision(BaseModel):
    """Dedup decision after deterministic validation and fallback."""

    mode: Literal["exact_full_row", "exact_key"]
    key_columns: list[str] = Field(default_factory=list)
    column_semantics: dict[str, ColumnSemanticDescriptor] = Field(default_factory=dict)
    ignore_columns: list[str] = Field(default_factory=list)
    fuzzy_plan: FuzzyExecutionPlan | None = None
    decision_source: Literal["llm", "planner_fallback", "profile_fallback", "safe_default"]
    confidence: float | None = None
    reasoning_summary: str = ""
    keep_rule: Literal["keep_most_complete", "keep_first", "keep_last"] = "keep_most_complete"
    validation_notes: list[str] = Field(default_factory=list)
    unresolved_collisions: list[dict[str, Any]] = Field(default_factory=list)

    def to_trace(self, *, context_hash: str) -> DedupDecisionTrace:
        """Project the validated decision into the persisted trace model."""

        return DedupDecisionTrace(
            decision_source=self.decision_source,
            column_semantics={
                column: descriptor.model_dump(mode="json")
                for column, descriptor in self.column_semantics.items()
            },
            ignore_columns=list(self.ignore_columns),
            fuzzy_plan=self.fuzzy_plan.model_dump(mode="json") if self.fuzzy_plan else None,
            confidence=self.confidence,
            reasoning_summary=self.reasoning_summary,
            validation_notes=list(self.validation_notes),
            context_hash=context_hash,
        )


class FuzzyCandidate(BaseModel):
    """A candidate pair surfaced by fuzzy blocking."""

    row_index_a: int
    row_index_b: int
    blocking_spec_id: str
    field: str
    similarity_score: float
    blocking_key: str
    semantic_label: str
    cross_script: bool = False
    support_matches: list[str] = Field(default_factory=list)
    reject_conflicts: list[str] = Field(default_factory=list)
    resolution: Literal["supported", "review", "rejected"] = "review"


class FuzzyCandidateSet(BaseModel):
    """In-memory summary of fuzzy candidates."""

    candidates: list[FuzzyCandidate] = Field(default_factory=list)
    oversized_buckets: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    supported_count: int = 0
    review_count: int = 0
    rejected_count: int = 0

    @property
    def total_count(self) -> int:
        return len(self.candidates)

@dataclass(slots=True)
class FuzzyBlockingConfig:
    """Deterministic fallback defaults for fuzzy execution planning."""

    company_ngram_size: int = 3
    person_ngram_size: int = 2
    address_shingle_size: int = 2
    company_threshold: float = 0.5
    person_threshold: float = 0.4
    address_threshold: float = 0.6
    max_bucket_size: int = 500
