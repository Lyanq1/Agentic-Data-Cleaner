"""State models for specific agent workers and their results."""

from typing import Any, Literal
from pydantic import BaseModel, Field

class WorkerStateDetail(BaseModel):
    status: Literal["pending", "running", "done", "failed"]
    retries: int = 0
    error_log: list[str] = Field(default_factory=list)

class WorkerStates(BaseModel):
    last_completed_agent: str | None = None
    dedup_agent: WorkerStateDetail
    null_agent: WorkerStateDetail
    typecast_agent: WorkerStateDetail


class DedupDecisionTrace(BaseModel):
    decision_source: Literal["llm", "planner_fallback", "profile_fallback", "safe_default"]
    column_semantics: dict[str, dict[str, Any]] = Field(default_factory=dict)
    ignore_columns: list[str] = Field(default_factory=list)
    fuzzy_plan: dict[str, Any] | None = None
    confidence: float | None = None
    reasoning_summary: str = ""
    validation_notes: list[str] = Field(default_factory=list)
    context_hash: str


class DedupPreviewGroup(BaseModel):
    group_key: dict[str, Any] = Field(default_factory=dict)
    row_count: int = 0
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)


class DedupPreviewSummary(BaseModel):
    duplicate_rows: int = 0
    duplicate_groups: int = 0
    sample_groups: list[DedupPreviewGroup] = Field(default_factory=list)


class DedupStrategyReview(BaseModel):
    review_type: Literal["dedup_strategy_review"] = "dedup_strategy_review"
    proposed_mode: Literal["exact_full_row", "exact_key"]
    proposed_key_columns: list[str] = Field(default_factory=list)
    suggested_identifier_columns: list[str] = Field(default_factory=list)
    ignored_columns: list[str] = Field(default_factory=list)
    keep_rule: Literal["keep_most_complete", "keep_first", "keep_last"] = "keep_most_complete"
    questions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    preview: DedupPreviewSummary = Field(default_factory=DedupPreviewSummary)

class DeduplicationResult(BaseModel):
    applied_modes: list[Literal["exact_full_row", "exact_key"]] = Field(default_factory=list)
    key_columns: list[str] = Field(default_factory=list)
    keep_strategy: str = "first"
    source_path: str
    output_path: str
    before_row_count: int
    after_row_count: int
    dropped_row_count: int
    full_row_duplicate_count: int = 0
    key_duplicate_count: int = 0
    duplicate_group_count: int = 0
    notes: list[str] = Field(default_factory=list)
    decision_trace: DedupDecisionTrace | None = None
    pending_strategy_review: DedupStrategyReview | None = None
