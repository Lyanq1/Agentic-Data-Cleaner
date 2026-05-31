"""State models for the LangGraph pipeline."""
from typing import Annotated, Any, Dict, List, Optional, Literal
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage
from pydantic import BaseModel, Field

from app.agents.roles import AgentRole

### helper function ###
def append_list(left: list | None, right: list | Any | None) -> list:
    if left is None:
        left = []
    if right is None:
        return left
    if isinstance(right, list):
        return left + right
    return left + [right]

### Pydantic Models for State Requirements ###
class NullHandlingReq(BaseModel):
    column: str
    strategy: Literal["fill_mean", "fill_median", "fill_mode", "fill_constant", "drop_row"]
    fill_value: Optional[Any] = None

class DeduplicationReq(BaseModel):
    enabled: bool
    key_columns: List[str]

class TypecastReq(BaseModel):
    column: str
    target_type: Literal["int", "float", "str", "bool", "date", "datetime"]

class AdditionalRequirementMarkdown(BaseModel):
    null_handling: List[NullHandlingReq] = Field(default_factory=list)
    deduplication: Optional[DeduplicationReq] = None
    typecast: List[TypecastReq] = Field(default_factory=list)
    other: List[str] = Field(default_factory=list)

### Pydantic Models for Profiling & Context ###
class ColumnStatProfile(BaseModel):
    column_name: str
    dtype: str
    null_count: int
    null_rate: float
    unique_count: int
    unique_ratio: float
    sample_values: List[Any] = Field(default_factory=list)
    detected_patterns: List[str] = Field(default_factory=list)
    interpretation: List[str] = Field(default_factory=list)
    numeric_stats: Optional[Dict[str, Any]] = None
    categorical_stats: Optional[Dict[str, Any]] = None

class StatisticalProfile(BaseModel):
    source: str
    total_rows: int
    total_columns: int
    pk_candidates: List[str] = Field(default_factory=list)
    near_unique_columns: List[str] = Field(default_factory=list)
    categorical_columns: List[str] = Field(default_factory=list)
    high_null_columns: List[str] = Field(default_factory=list)
    columns: List[ColumnStatProfile] = Field(default_factory=list)

class ColumnSemanticDetail(BaseModel):
    allow_missing: bool
    thought_missing: str
    expect_type: str
    thought_type: str
    potential_dmv: List[str] = Field(default_factory=list)
    thought_dmv: str

class ColumnSummary(BaseModel):
    description: str
    semantic_detail: ColumnSemanticDetail

class ColumnGroup(BaseModel):
    group_name: str
    description: str

class SemanticContext(BaseModel):
    table_summary: str
    column_groups: List[ColumnGroup] = Field(default_factory=list)
    columns_summary: Dict[str, ColumnSummary] = Field(default_factory=dict)

### Pydantic Models for Validation & Planning ###
class ValidationIssue(BaseModel):
    requirement: str
    column: Optional[str] = None
    status: Literal["feasible", "infeasible", "warning"]
    reason: str

class InputValidationResult(BaseModel):
    passed: bool
    issues: List[ValidationIssue] = Field(default_factory=list)
    summary: str

class TaskDetail(BaseModel):
    task_id: str
    agent: AgentRole
    skip: bool
    skip_reason: Optional[str] = None
    columns: List[str] = Field(default_factory=list)
    strategy: Dict[str, Any] = Field(default_factory=dict)

class ExecutionPlan(BaseModel):
    task_list: List[TaskDetail] = Field(default_factory=list)
    plan_summary: str

### Pydantic Models for Workers & Checkpoints ###
class WorkerStateDetail(BaseModel):
    status: Literal["pending", "running", "done", "failed"]
    retries: int = 0
    error_log: List[str] = Field(default_factory=list)

class WorkerStates(BaseModel):
    last_completed_agent: Optional[str] = None
    dedup_agent: WorkerStateDetail
    null_agent: WorkerStateDetail
    typecast_agent: WorkerStateDetail

class ValidationResultItem(BaseModel):
    agent: str
    task_id: str
    passed: bool
    failed_rules: List[str] = Field(default_factory=list)
    timestamp: str

### TypedDict for the LangGraph State ###
class GlobalState(TypedDict):
    # Core Routing & Messages
    messages: Annotated[list[AnyMessage], add_messages]
    next_node: Optional[str]

    # Project Context
    project_id: Optional[str]
    dataset_path: Optional[str]
    user_prompt: Optional[str]

    # Data Schema and Requirements
    dataset_schema: Optional[Dict[str, Any]]
    dataset_version: Optional[str]
    raw_requirement_input: Optional[str]
    additional_requirement_markdown: Optional[AdditionalRequirementMarkdown]

    # Data References & Progress
    current_dataset_version: Optional[str]
    physical_dataframe_path: Optional[str]
    current_step: Optional[str]
    completed_steps: Annotated[List[str], append_list]

    # Intelligence & Validation
    statistical_profile: Optional[StatisticalProfile]
    semantic_context: Optional[SemanticContext]
    input_validation_result: Optional[InputValidationResult]
    
    # Execution & Routing
    execution_plan: Optional[ExecutionPlan]
    worker_states: Optional[WorkerStates]
    validation_results: Annotated[List[ValidationResultItem], append_list]
    
    # Control flow variables
    current_task_idx: Optional[int]
    retry_count: Optional[int]

    # HITL Fields
    hitl_checkpoint: Optional[int]
    hitl_status: Optional[Literal["pending", "approved", "rejected"]]
    hitl_feedback: Optional[str]

    # Global Shared Errors
    global_errors: Annotated[List[str], append_list]

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
    current_task: Optional[str]
    status: AgentStatus

    # Operational metrics & outputs
    local_result: Optional[Dict[str, Any]]
    metrics: Optional[Dict[str, Any]]
    agent_errors: Annotated[List[str], append_list]
