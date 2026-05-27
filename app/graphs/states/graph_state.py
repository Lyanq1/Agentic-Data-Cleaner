"""State models for the LangGraph pipeline."""
from typing import Annotated, Any, Dict, List, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage


### helper function ###
def append_list(left: list | None, right: list | Any | None) -> list:
    if left is None:
        left = []
    if right is None:
        return left
    if isinstance(right, list):
        return left + right
    return left + [right]

class GlobalState(TypedDict):
    # core routing & messages
    messages: Annotated[list[AnyMessage], add_messages]
    next_node: Optional[str]  # route to the next node

    # project context & configuration
    project_id: Optional[str]
    dataset_path: Optional[str]
    
    # centralized data references
    dataset_schema: Optional[Dict[str, Any]]
    data_profile: Optional[Dict[str, Any]]
    
    # cleaning plan & progress tracking
    cleaning_plan: Optional[List[str]]
    current_step: Optional[str]
    completed_steps: Annotated[List[str], append_list]
    
    # shared errors
    global_errors: Annotated[List[str], append_list]

class AgentStatus:
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    ERRORED = "errored"

class AgentRole:
    PLANNER = "planner"
    EXECUTOR = "executor"
    REVIEWER = "reviewer"

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

    # Operational  metrics & outputs
    local_result: Optional[Dict[str, Any]]
    metrics: Optional[Dict[str, Any]]
    agent_errors: Annotated[List[str], append_list]
