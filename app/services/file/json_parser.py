"""JSON / JSONL parser — normalises nested objects into a flat tabular structure."""

from pathlib import Path

import pandas as pd

from app.core.exceptions import IngestionError
from app.services.file.base import BaseParser


class JSONParser(BaseParser):
    SUPPORTED_EXTENSIONS = {".json", ".jsonl", ".ndjson"}

    def supports(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def parse(self, file_path: Path) -> pd.DataFrame:
        try:
            suffix = file_path.suffix.lower()
            if suffix in {".jsonl", ".ndjson"}:
                df = pd.read_json(file_path, lines=True, dtype=str)
            else:
                df = pd.read_json(file_path, dtype=str)

            # Flatten one level of nesting — deeper nesting flagged in profiling
            if isinstance(df.iloc[0] if len(df) > 0 else None, dict):
                df = pd.json_normalize(df.to_dict(orient="records"))

            return df.astype(str)
        except Exception as e:
            raise IngestionError(f"Failed to parse JSON file: {e}") from e
