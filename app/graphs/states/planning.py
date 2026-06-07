"""State models for planning and tasks."""

from typing import Any, Literal
from pydantic import BaseModel, Field

from app.agents.roles import AgentRole
from app.graphs.states.output_validation import TaskVerification

class PlanMetadata(BaseModel):
    plan_id: str
    plan_version: int = 1
    created_at: str

class GlobalConstraints(BaseModel):
    max_retries_per_task: int = 3
    preserve_columns: list[str] = Field(default_factory=list)

class DedupStrategy(BaseModel):
    dedup_scope: Literal["row_level", "key_level", "entity_level"]
    duplicate_types: list[Literal["exact_row", "duplicate_key", "fuzzy_entity"]]
    primary_keys: list[str] = Field(default_factory=list)
    exact_match: dict[str, Any] = Field(default_factory=dict)
    key_based: dict[str, Any] = Field(default_factory=dict)
    normalization: dict[str, list[str]] = Field(default_factory=dict)
    fuzzy_matching: dict[str, Any] = Field(default_factory=dict)
    llm_review: dict[str, Any] = Field(default_factory=dict)
    output_artifacts: dict[str, Any] = Field(default_factory=dict)

class NullStrategy(BaseModel):
    per_column: dict[str, dict[str, Any]] = Field(default_factory=dict)

class TypeStrategy(BaseModel):
    per_column: dict[str, dict[str, Any]] = Field(default_factory=dict)

class ClarificationRequirement(BaseModel):
    question: str
    user_answer: str

class ColumnTaskContext(BaseModel):
    statistical: dict[str, Any]
    semantic: dict[str, Any]

class TaskInputs(BaseModel):
    read_path_key: str = "physical_dataframe_path"
    column_context: dict[str, ColumnTaskContext] = Field(default_factory=dict)
    relevant_clarifications: list[ClarificationRequirement] = Field(default_factory=list)
    relevant_action_plan: str | None = None

class TaskOutputs(BaseModel):
    write_path_key: str = "physical_dataframe_path"
    expected_artifacts: list[str] = Field(default_factory=list)
    must_preserve_row_count: bool = False

class TaskDetail(BaseModel):
    task_id: str
    agent: AgentRole
    skip: bool
    skip_reason: str | None = None
    columns: list[str] = Field(default_factory=list)
    rationale: str | None = None
    execution_mode: Literal["tools_only", "tools_then_llm", "llm_assist"] | None = None
    tool_sequence_hint: list[str] | None = None
    inputs: TaskInputs | None = None
    outputs: TaskOutputs | None = None
    verification: TaskVerification | None = None
    strategy: DedupStrategy | NullStrategy | TypeStrategy | dict[str, Any] | None = None

class TaskDetailWrapper(BaseModel):
    work_order: TaskDetail

class ExecutionPlan(BaseModel):
    metadata: PlanMetadata
    plan_summary: str
    assumptions: list[str] = Field(default_factory=list)
    global_constraints: GlobalConstraints
    task_list: list[TaskDetailWrapper] = Field(default_factory=list)
