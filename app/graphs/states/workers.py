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
    column_roles: dict[str, str] = Field(default_factory=dict)
    ignore_columns: list[str] = Field(default_factory=list)
    confidence: float | None = None
    reasoning_summary: str = ""
    validation_notes: list[str] = Field(default_factory=list)
    context_hash: str


class DeduplicationReviewCase(BaseModel):
    case_id: str
    candidate_type: Literal["weak_single_key", "name_only", "cross_script_name", "fuzzy_candidate"]
    row_fingerprints: list[str] = Field(default_factory=list)
    row_indices: list[int] = Field(default_factory=list)
    row_data: list[dict[str, Any]] = Field(default_factory=list)
    matching_fields: list[str] = Field(default_factory=list)
    conflicting_fields: list[str] = Field(default_factory=list)
    agent_rationale: str = ""
    suggested_action: Literal["merge", "do_not_merge"] | None = None

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
    pending_review_cases: list[DeduplicationReviewCase] = Field(default_factory=list)
