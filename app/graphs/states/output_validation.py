"""State models for output validation and task verification."""

from typing import Any, Literal
from pydantic import BaseModel, Field

class ValidationCheck(BaseModel):
    type: str
    column: str | None = None
    columns: Any | None = None
    expected: Any | None = None
    threshold: float | None = None
    severity: Literal["error", "warning"] = "error"
    params: dict[str, Any] = Field(default_factory=dict)

class TaskVerification(BaseModel):
    validation_scope: Literal["post_task"] = "post_task"
    validator_mode: Literal["pandas_custom"] = "pandas_custom"
    baseline_metrics: dict[str, Any] = Field(default_factory=dict)
    checks: list[ValidationCheck] = Field(default_factory=list)
    success_metrics: dict[str, Any] = Field(default_factory=dict)
    failure_policy: dict[str, str] = Field(default_factory=dict)
    evidence_required: list[str] = Field(default_factory=list)

class ValidationResultItem(BaseModel):
    agent: str
    task_id: str
    passed: bool
    failed_rules: list[str] = Field(default_factory=list)
    metrics_observed: dict[str, Any] = Field(default_factory=dict)
    expected_metrics: dict[str, Any] = Field(default_factory=dict)
    artifact_errors: list[str] = Field(default_factory=list)
    recommended_next_action: Literal[
        "pass", "retry_worker", "retry_worker_with_modified_params", "replan", "hitl"
    ] = "pass"
    replan_hints: dict[str, Any] = Field(default_factory=dict)
    timestamp: str
