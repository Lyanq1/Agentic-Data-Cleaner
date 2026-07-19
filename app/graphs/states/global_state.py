"""State models for the LangGraph pipeline."""

from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from app.graphs.states.profiler_state import StatisticalProfile
from app.graphs.states.input_validation import InputValidationResult
from app.graphs.states.planning import ExecutionPlan
from app.graphs.states.profiles import SemanticProfile
from app.graphs.states.workers import WorkerStates
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

def sum_metrics(left: dict[str, int] | None, right: dict[str, int] | None) -> dict[str, int]:
    if not left:
        left = {"total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0}
    if not right:
        return left
    return {k: left.get(k, 0) + right.get(k, 0) for k in set(left) | set(right)}


def merge_agent_logs(
    left: dict[str, Any] | None, right: dict[str, Any] | None
) -> dict[str, Any]:
    if left is None:
        left = {}
    if right is None:
        return left

    # Create a deep copy of the left dict to avoid side-effects
    new_dict = {}
    for k, v in left.items():
        if isinstance(v, dict):
            new_dict[k] = dict(v)
            if "logs" in v:
                new_dict[k]["logs"] = list(v["logs"])
        elif isinstance(v, list):
            new_dict[k] = list(v)
        else:
            new_dict[k] = v

    # Merge right updates into new_dict
    for k, v in right.items():
        if k not in new_dict:
            if isinstance(v, dict):
                new_dict[k] = dict(v)
                if "logs" in v:
                    new_dict[k]["logs"] = list(v["logs"])
            elif isinstance(v, list):
                new_dict[k] = list(v)
            else:
                new_dict[k] = v
        else:
            existing = new_dict[k]
            if isinstance(existing, dict) and isinstance(v, dict):
                merged_sub = dict(existing)
                for sub_k, sub_v in v.items():
                    if sub_k == "logs" and "logs" in merged_sub and isinstance(merged_sub["logs"], list) and isinstance(sub_v, list):
                        merged_sub["logs"] = merged_sub["logs"] + sub_v
                    else:
                        merged_sub[sub_k] = sub_v
                new_dict[k] = merged_sub
            elif isinstance(existing, list) and isinstance(v, list):
                new_dict[k] = existing + v
            else:
                new_dict[k] = v

    return new_dict

### TypedDict for the LangGraph State ###
class GlobalState(TypedDict):
    # Core Routing & Messages
    messages: Annotated[list[AnyMessage], add_messages]
    next_node: str | None

    # Project Context
    project_id: str | None
    session_id: str | None
    dataset_path: str | None
    clean_dataset_path: str | None
    original_filename: str | None
    user_prompt: str | None

    # Data Schema and Requirements
    dataset_schema: dict[str, Any] | None
    raw_requirement_input: str | None

    # Data References & Progress
    current_dataset_version: str | None
    physical_dataframe_path: str | None
    path_file_to_validate: str | None
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
    agent_logs: Annotated[dict[str, Any], merge_agent_logs]

    # Control flow variables
    current_task_idx: int | None
    retry_count: int | None
    last_validation_error: str | None
    failed_task_id: str | None
    replan_reason: str | None

    # HITL Fields
    hitl_checkpoint: int | None
    hitl_status: Literal["pending", "approved", "rejected"] | None

    # Global Shared Errors
    global_errors: Annotated[list[str], append_list]
    
    # Evaluation Metrics
    f1_metrics: dict[str, Any] | None
    
    # Store original datetime/date formats
    original_datetime_formats: dict[str, dict[str, str]] | None

    # Token Usage Metrics
    token_metrics: Annotated[dict[str, int], sum_metrics]

    # Benchmark Flow Mode & References
    pipeline_mode: Literal["interactive", "benchmark"] | None
    ground_truth_path: str | None



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
