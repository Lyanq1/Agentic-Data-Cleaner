"""Normalizer — converts any parsed DataFrame into the canonical Parquet format.

All agents read from and write to Parquet to avoid repeated parsing overhead.
Output conversion back to the original format is handled at the very end by
``export_from_canonical``.
"""
from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path
from uuid import uuid4

import pandas as pd

from app.config.config import get_settings
from app.exceptions.ingestion_exceptions import IngestionError
from app.ingestion.parsers import CSVParser, ExcelParser, JSONParser
from app.ingestion.parsers.base import BaseParser

logger = logging.getLogger(__name__)


class InputFormat(str, Enum):
    """Supported input file formats."""

    CSV = "csv"
    EXCEL = "excel"
    JSON = "json"


_PARSERS: list[BaseParser] = [CSVParser(), ExcelParser(), JSONParser()]

_EXT_TO_FORMAT: dict[str, InputFormat] = {
    ".csv": InputFormat.CSV, ".tsv": InputFormat.CSV, ".txt": InputFormat.CSV,
    ".xlsx": InputFormat.EXCEL, ".xls": InputFormat.EXCEL, ".xlsm": InputFormat.EXCEL,
    ".json": InputFormat.JSON, ".jsonl": InputFormat.JSON, ".ndjson": InputFormat.JSON,
}


def detect_format(file_path: Path) -> InputFormat:
    """Detect the input format from the file extension."""
    ext = file_path.suffix.lower()
    if ext not in _EXT_TO_FORMAT:
        raise IngestionError(f"Unsupported file extension: {ext}")
    return _EXT_TO_FORMAT[ext]


def ingest_to_canonical(
    file_path: Path,
    output_dir: Path | None = None,
) -> tuple[Path, InputFormat, dict | None]:
    """Parse any supported file and write it as Parquet.

    Returns:
        (canonical_parquet_path, detected_format, schema)
    """
    fmt = detect_format(file_path)

    parser = next((p for p in _PARSERS if p.supports(file_path)), None)
    if parser is None:
        raise IngestionError(f"No parser available for: {file_path.name}")

    logger.info(f"Ingesting {file_path.name} (format={fmt.value})")
    df = parser.parse(file_path)
    schema = parser.get_schema(file_path)

    if df.empty:
        raise IngestionError(f"File '{file_path.name}' produced an empty DataFrame.")


    settings = get_settings()
    out_dir = output_dir or Path(settings.upload_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    session_id = uuid4()
    canonical_path = out_dir / f"{session_id.hex}.parquet"
    df.to_parquet(canonical_path, index=False, engine="pyarrow")
    logger.info(f"Canonical Parquet saved: {canonical_path} ({len(df)} rows × {len(df.columns)} cols)")

    # Save to PostgreSQL for lineage tracking using JSONB
    from app.core.database import SessionLocal, init_db
    from app.models.lineage import Session, LineageVersion, DatasetRecord
    
    # Initialize DB schema if not exists
    init_db()

    db = SessionLocal()
    try:
        db_session = Session(id=session_id, dataset_name=file_path.name)
        db.add(db_session)
        
        db_version = LineageVersion(
            session_id=session_id,
            version=1,
            agent_name="ingestion_agent",
            description="Initial data ingestion"
        )
        db.add(db_version)
        
        # Flush the session and version to the database so they exist for the foreign keys
        db.flush()
        
        # Convert DataFrame to records and bulk save
        records_dict = df.to_dict(orient="records")
        clean_records = []
        for row in records_dict:
            clean_row = {}
            for k, v in row.items():
                if pd.isna(v):
                    clean_row[k] = None
                else:
                    clean_row[k] = v
            clean_records.append(clean_row)

        db_records = [
            DatasetRecord(
                session_id=session_id,
                version=1,
                data=row,
                row_index=i
            )
            for i, row in enumerate(clean_records)
        ]
        db.bulk_save_objects(db_records)
        db.commit()
        logger.info(f"Data saved to PostgreSQL for session {session_id} (version 1).")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save data to PostgreSQL: {e}")
        raise
    finally:
        db.close()

    return canonical_path, fmt, schema



def export_from_canonical(
    canonical_path: Path,
    target_format: InputFormat,
    output_dir: Path,
) -> Path:
    """Convert a canonical Parquet back to the target user-facing format."""
    df = pd.read_parquet(canonical_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(canonical_path).stem

    if target_format == InputFormat.CSV:
        out = output_dir / f"{stem}.csv"
        df.to_csv(out, index=False)
    elif target_format == InputFormat.EXCEL:
        out = output_dir / f"{stem}.xlsx"
        df.to_excel(out, index=False, engine="openpyxl")
    elif target_format == InputFormat.JSON:
        out = output_dir / f"{stem}.json"
        df.to_json(out, orient="records", indent=2)
    else:
        raise IngestionError(f"Export to format '{target_format}' not yet supported.")

    return out
