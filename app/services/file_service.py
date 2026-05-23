"""FileService — handle file upload, validation, and path resolution."""
from pathlib import Path
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".parquet"}


class FileService:
    """Handles file uploads and path management."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.upload_dir = Path(self.settings.upload_dir)
        self.output_dir = Path(self.settings.output_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def validate_file(self, filename: str, size_bytes: int) -> None:
        """Validate file extension and size."""
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"Unsupported file type '{ext}'. Allowed: {ALLOWED_EXTENSIONS}")
        max_bytes = self.settings.max_upload_size_mb * 1024 * 1024
        if size_bytes > max_bytes:
            raise ValueError(f"File size {size_bytes} exceeds limit of {max_bytes} bytes")

    def get_upload_path(self, job_id: str, filename: str) -> Path:
        """Return the absolute path for an uploaded file."""
        job_dir = self.upload_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir / filename

    def get_output_path(self, job_id: str, filename: str) -> Path:
        """Return the absolute path for an output file."""
        job_dir = self.output_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir / filename
