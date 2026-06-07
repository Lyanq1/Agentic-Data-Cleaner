"""State models for the LangGraph pipeline."""

from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from app.graphs.states.profiler_state import StatisticalProfile
from app.graphs.states.input_validation import InputValidationResult
from app.graphs.states.planning import ExecutionPlan
from app.graphs.states.profiles import SemanticProfile
from app.graphs.states.workers import WorkerStates, DeduplicationResult
from app.graphs.states.output_validation import ValidationResultItem

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
