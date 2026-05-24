from enum import StrEnum

class AgentRole(StrEnum):
    SUPERVISOR = "supervisor"
    COLUMN_SELECTOR = "column_selector"
    DUPLICATE_HANDLER = "duplicate_handler"
    NULL_TYPE_HANDLER = "null_type_handler"
    VALIDATOR = "validator"
    INPUT_VALIDATOR = "input_validator"
    REPORTER = "reporter"