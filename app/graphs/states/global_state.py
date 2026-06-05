"""State models for the LangGraph pipeline."""

from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field, field_validator

from app.agents.roles import AgentRole


### helper function ###
def append_list(
    left: list[Any] | None, right: list[Any] | Any | None  # noqa: ANN401
) -> list[Any]:
    if left is None:
        left = []
    if right is None:
        return left
    if isinstance(right, list):
        return left + right
    return left + [right]


### Pydantic Models for Profiling & Context ###
class ColumnStatProfile(BaseModel):
    column_name: str
    dtype: str
    null_count: int
    null_rate: float
    unique_count: int
    unique_ratio: float
    sample_values: list[Any] = Field(default_factory=list)
    detected_patterns: list[str] = Field(default_factory=list)
    interpretation: list[str] = Field(default_factory=list)
    numeric_stats: dict[str, Any] | None = None
    categorical_stats: dict[str, Any] | None = None


class StatisticalProfile(BaseModel):
    source: str
    total_rows: int
    total_columns: int
    pk_candidates: list[str] = Field(default_factory=list)
    near_unique_columns: list[str] = Field(default_factory=list)
    categorical_columns: list[str] = Field(default_factory=list)
    high_null_columns: list[str] = Field(default_factory=list)
    duplicate_rows: int = 0
    columns: list[ColumnStatProfile] = Field(default_factory=list)





### Pydantic Models for Validation & Planning ###
class StrategyQuestion(BaseModel):
    question: str = Field(description="The strategy question text.")
    options: list[str] = Field(description="Exactly 3 distinct options.")
    consequences: Any | None = Field(default=None, description="Consequences of each option.")
    answer: str | None = Field(default=None, description="The user's selected option/answer.")


class InsightQuestion(BaseModel):
    question: str = Field(description="The insight question text.")
    insight: str = Field(description="The semantic insight revealed.")
    confirm: str = Field(description="The yes/no confirmation ask.")
    answer: str | None = Field(
        default=None, description="The user's answer ('yes', 'no', or comment)."
    )


class NullClarifications(BaseModel):
    Q1_strategy: StrategyQuestion | None = None
    Q2_semantic_insight: InsightQuestion | None = None
    Q3_semantic_insight: InsightQuestion | None = None


class DuplicateClarifications(BaseModel):
    Q1_strategy: StrategyQuestion | None = None
    Q2_semantic_insight: InsightQuestion | None = None
    Q3_semantic_insight: InsightQuestion | None = None


class TypecastClarifications(BaseModel):
    Q1_semantic_insight: InsightQuestion | None = None
    Q2_semantic_insight: InsightQuestion | None = None
    Q3_semantic_insight: InsightQuestion | None = None


class ClarificationIssues(BaseModel):
    null: NullClarifications | None = None
    duplicate: DuplicateClarifications | None = None
    typecast: TypecastClarifications | None = None


class ActionPlan(BaseModel):
    null: str | None = None
    duplicate: str | None = None
    typecast: str | None = None

    @field_validator("null", "duplicate", "typecast", mode="before")
    @classmethod
    def convert_to_string(cls, v: Any) -> str | None:  # noqa: ANN401
        if v is None:
            return None
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            return " | ".join(f"{k}: {val}" for k, val in v.items())
        if isinstance(v, list):
            return ", ".join(str(item) for item in v)
        return str(v)


class InputValidationResult(BaseModel):
    """Structured output expected from the Input Validator LLM."""

    status: Literal["ready", "needs_clarification"] = Field(
        description="The status of the validation. 'ready' or 'needs_clarification'."
    )
    reasoning: str = Field(description="Brief reasoning explaining the status.")
    resolved_by_user: list[str] = Field(
        default_factory=list,
        description="List of issues and columns resolved by the user's request.",
    )
    action_plan: ActionPlan | None = Field(
        default=None, description="The plan for each issue if status is 'ready'."
    )
    clarifications: ClarificationIssues | None = Field(
        default=None,
        description="Clarifications needed per active issue if status is 'needs_clarification'.",
    )


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
    validator_mode: Literal["pandera", "custom", "pandera_plus_custom"] = "pandera"
    baseline_metrics: dict[str, Any] = Field(default_factory=dict)
    pandera_checks: list[ValidationCheck] = Field(default_factory=list)
    custom_checks: list[ValidationCheck] = Field(default_factory=list)
    success_metrics: dict[str, Any] = Field(default_factory=dict)
    failure_policy: dict[str, str] = Field(default_factory=dict)
    evidence_required: list[str] = Field(default_factory=list)


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


### Pydantic Models for Workers & Checkpoints ###
class WorkerStateDetail(BaseModel):
    status: Literal["pending", "running", "done", "failed"]
    retries: int = 0
    error_log: list[str] = Field(default_factory=list)


class WorkerStates(BaseModel):
    last_completed_agent: str | None = None
    dedup_agent: WorkerStateDetail
    null_agent: WorkerStateDetail
    typecast_agent: WorkerStateDetail


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


class ColumnSemanticProfileDetail(BaseModel):
    description: str = Field(description="A clear business description of the column.")
    logical_group: str = Field(
        description="The logical group this column belongs to (e.g. Identity, Pricing, Address)."
    )
    relationships: list[str] = Field(
        default_factory=list,
        description=(
            "Cross-column relationships or functional dependencies "
            "(e.g., 'zip_code -> city')."
        ),
    )
    allow_missing: bool = Field(
        description="True if missing/null values are acceptable from a business standpoint."
    )
    allow_missing_reason: str = Field(default="", description="Reasoning explaining allow_missing.")
    expected_type: str = Field(
        description="Ideal semantic type: int | float | str | bool | date | datetime."
    )
    expected_type_reason: str = Field(default="", description="Reasoning explaining expected_type.")
    potential_dmv: list[str] = Field(
        default_factory=list, description="List of common disguised missing values detected."
    )
    potential_dmv_reason: str = Field(default="", description="Reasoning explaining potential_dmv.")
    expected_str_pattern: str | None = Field(
        default=None, description="Expected regex or string format pattern."
    )
    expected_str_pattern_reason: str | None = Field(
        default=None, description="Reasoning explaining expected_str_pattern."
    )

    # Combined Semantic Review / Quality Audit
    is_error: bool = Field(
        description=(
            "True if statistical reality deviates from business rules "
            "or has other anomalies."
        )
    )
    error_types: list[str] = Field(
        default_factory=list,
        description=(
            "Subset of 'missing' | 'type_mismatch' | 'dmv' | "
            "'string_outlier' | 'numeric_outlier'."
        ),
    )
    error_reason: str | None = Field(
        default=None, description="Detailed explanation of the error if is_error is True."
    )


class SemanticProfile(BaseModel):
    table_summary: str = Field(
        description="Concise description of the overall business purpose of the dataset."
    )
    thinking: str = Field(
        default="", description="Chain of thought thinking behind the semantic profile."
    )
    columns: dict[str, ColumnSemanticProfileDetail] = Field(
        default_factory=dict, description="Detailed semantic profile per column."
    )


### TypedDict for the LangGraph State ###
class GlobalState(TypedDict):
    # Core Routing & Messages
    messages: Annotated[list[AnyMessage], add_messages]
    next_node: str | None

    # Project Context
    project_id: str | None
    session_id: str | None
    dataset_path: str | None
    user_prompt: str | None

    # Data Schema and Requirements
    dataset_schema: dict[str, Any] | None
    dataset_version: str | None
    raw_requirement_input: str | None

    # Data References & Progress
    current_dataset_version: str | None
    physical_dataframe_path: str | None
    current_step: str | None
    completed_steps: Annotated[list[str], append_list]

    # Intelligence & Validation
    statistical_profile: StatisticalProfile | None
    semantic_profile: SemanticProfile | None
    input_validation_result: InputValidationResult | None

    # Execution & Routing
    execution_plan: ExecutionPlan | None
    task_list: list[str]
    worker_states: WorkerStates | None
    worker_outputs: dict[str, Any] | None
    validation_results: Annotated[list[ValidationResultItem], append_list]
    deduplication_result: DeduplicationResult | None

    # Control flow variables
    current_task_idx: int | None
    retry_count: int | None
    last_validation_error: str | None
    failed_task_id: str | None
    replan_reason: str | None

    # HITL Fields
    hitl_checkpoint: int | None
    hitl_status: Literal["pending", "approved", "rejected"] | None
    hitl_feedback: str | None

    # Global Shared Errors
    global_errors: Annotated[list[str], append_list]


class AgentStatus:
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    ERRORED = "errored"


class AgentState(TypedDict):
    """State for an individual agent in the workflow.

    Captures individual progress, memory, task status, and operational metrics.
    """

    # agent identification
    agent_id: str

    # local memory
    agent_messages: Annotated[list[AnyMessage], add_messages]

    # task execution
    current_task: str | None
    status: AgentStatus

    # Operational metrics & outputs
    local_result: dict[str, Any] | None
    metrics: dict[str, Any] | None
    agent_errors: Annotated[list[str], append_list]
