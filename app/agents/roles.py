"""Definitions for reusable agent roles and names."""
from enum import Enum

class AgentRole(str, Enum):
    """Enumeration of all agent roles/names across the pipeline."""
    
    # Core orchestration agents
    PROFILER = "profiler"
    INPUT_VALIDATOR = "input_validator"
    PLANNER = "planner"
    VALIDATOR = "validator"
    REPORT_AGENT = "report_agent"
    
    # Execution / Worker agents
    DEDUP_AGENT = "dedup_agent"
    NULL_AGENT = "null_agent"
    TYPECAST_AGENT = "typecast_agent"
    
    # Abstract generic roles
