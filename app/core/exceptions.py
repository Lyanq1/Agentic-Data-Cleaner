class BaseAppException(Exception):
    """Base class for all custom exceptions in the application."""
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

class DatasetValidationError(BaseAppException):
    def __init__(self, message: str = "Dataset format is invalid."):
        super().__init__(message=message, status_code=400)

class JobNotFoundError(BaseAppException):
    def __init__(self, job_id: str):
        super().__init__(message=f"Job {job_id} not found.", status_code=404)

class IngestionError(BaseAppException):
    def __init__(self, message: str = "Error during file ingestion."):
        super().__init__(message=message, status_code=400)
