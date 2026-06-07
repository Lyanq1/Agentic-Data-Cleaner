"""State models for specific agent workers and their results."""

from typing import Literal
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
