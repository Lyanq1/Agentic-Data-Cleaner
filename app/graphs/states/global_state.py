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
    duplicate_rows: int = 0
    columns: List[ColumnStatProfile] = Field(default_factory=list)

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

class ColumnSemanticProfileDetail(BaseModel):
    description: str = Field(description="A clear business description of the column.")
    logical_group: str = Field(description="The logical group this column belongs to (e.g. Identity, Pricing, Address).")
    relationships: List[str] = Field(default_factory=list, description="Cross-column relationships or functional dependencies (e.g. 'zip_code -> city').")
    allow_missing: bool = Field(description="True if missing/null values are acceptable from a business standpoint.")
    allow_missing_reason: str = Field(default="", description="Reasoning explaining allow_missing.")
    expected_type: str = Field(description="Ideal semantic type: int | float | str | bool | date | datetime.")
    expected_type_reason: str = Field(default="", description="Reasoning explaining expected_type.")
    potential_dmv: List[str] = Field(default_factory=list, description="List of common disguised missing values detected.")
    potential_dmv_reason: str = Field(default="", description="Reasoning explaining potential_dmv.")
    expected_str_pattern: Optional[str] = Field(default=None, description="Expected regex or string format pattern.")
    expected_str_pattern_reason: Optional[str] = Field(default=None, description="Reasoning explaining expected_str_pattern.")
    
    # Combined Semantic Review / Quality Audit
    is_error: bool = Field(description="True if statistical reality deviates from business rules or has other anomalies.")
    error_types: List[str] = Field(default_factory=list, description="Subset of 'missing' | 'type_mismatch' | 'dmv' | 'string_outlier' | 'numeric_outlier'.")
    error_reason: Optional[str] = Field(default=None, description="Detailed explanation of the error if is_error is True.")

class SemanticProfile(BaseModel):
    table_summary: str = Field(description="Concise description of the overall business purpose of the dataset.")
    thinking: str = Field(default="", description="Chain of thought thinking behind the semantic profile.")
    columns: Dict[str, ColumnSemanticProfileDetail] = Field(default_factory=dict, description="Detailed semantic profile per column.")

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

    # Data References & Progress
    current_dataset_version: Optional[str]
    physical_dataframe_path: Optional[str]
    current_step: Optional[str]
    completed_steps: Annotated[List[str], append_list]

    # Intelligence & Validation
    statistical_profile: Optional[StatisticalProfile]
    semantic_profile: Optional[SemanticProfile]
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
