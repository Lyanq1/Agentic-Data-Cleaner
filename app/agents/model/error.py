from enum import StrEnum

class ErrorType(StrEnum):
    DUPLICATE = "duplicate"
    NULL = "null"
    TYPE_CAST = "type_cast"
    FORMAT = "format"