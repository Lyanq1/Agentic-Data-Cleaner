"""Application-wide custom exceptions."""


class IngestionError(Exception):
    """Raised when file ingestion (parsing, normalizing) fails."""