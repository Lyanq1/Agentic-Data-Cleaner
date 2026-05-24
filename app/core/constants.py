from enum import Enum, StrEnum

class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_FOR_HUMAN = "waiting_for_human"  # HITL pause
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class PipelineStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_HITL = "awaiting_hitl"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class ErrorType(StrEnum):
    DUPLICATE = "duplicate"
    NULL = "null"
    TYPE_CAST = "type_cast"
    FORMAT = "format"

class HITLDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    MODIFY = "modify"

class AgentRole(StrEnum):
    SUPERVISOR = "supervisor"
    COLUMN_SELECTOR = "column_selector"
    DUPLICATE_HANDLER = "duplicate_handler"
    NULL_TYPE_HANDLER = "null_type_handler"
    VALIDATOR = "validator"
    INPUT_VALIDATOR = "input_validator"
    REPORTER = "reporter"

class InputFormat(StrEnum):
    CSV = "csv"
    EXCEL = "excel"
    JSON = "json"
