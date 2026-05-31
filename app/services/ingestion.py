"""Ingestion service — handles file validation, saving, and canonical conversion."""
import logging
from dataclasses import dataclass
from pathlib import Path

from app.config.config import get_settings
from app.exceptions.ingestion_exceptions import IngestionError
from app.ingestion.normalizer import ingest_to_canonical, InputFormat

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    """Output of a successful ingestion."""

    canonical_path: str
    input_format: str
    original_filename: str
    size_mb: float
    data_schema: dict | None = None


class IngestionService:
    """Validate, persist, and convert uploaded files to canonical Parquet."""

    def __init__(self) -> None:
        self._settings = get_settings()

    def validate(self, filename: str, contents: bytes) -> None:
        """Validate file name and size. Raises ``IngestionError`` on failure."""
        if not filename:
            raise IngestionError("Filename is required.")

        size_mb = len(contents) / (1024 * 1024)
        if size_mb > self._settings.max_upload_size_mb:
            raise IngestionError(
                f"File too large: {size_mb:.1f}MB. Max: {self._settings.max_upload_size_mb}MB"
            )

    def save_and_convert(self, filename: str, contents: bytes) -> IngestionResult:
        """Save the raw file to disk and convert to canonical Parquet.

        Args:
            filename: Original filename from the upload.
            contents: Raw file bytes.

        Returns:
            IngestionResult with the canonical Parquet path and metadata.
        """
        upload_dir = Path(self._settings.upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Save raw upload
        raw_path = upload_dir / filename
        raw_path.write_bytes(contents)
        size_mb = len(contents) / (1024 * 1024)
        logger.info(f"Saved raw upload: {raw_path} ({size_mb:.1f}MB)")

        # Parse → Parquet
        canonical_path, input_format, schema = ingest_to_canonical(raw_path, output_dir=upload_dir)

        return IngestionResult(
            canonical_path=str(canonical_path),
            input_format=input_format.value,
            data_schema=schema,
            original_filename=filename,
            size_mb=round(size_mb, 2),
        )


def get_ingestion_service() -> IngestionService:
    """Factory for IngestionService."""
    return IngestionService()
