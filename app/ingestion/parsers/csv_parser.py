"""CSV parser — handles BOM, encoding detection, delimiter sniffing."""
from pathlib import Path

import chardet
import pandas as pd

from app.exceptions.ingestion_exceptions import IngestionError
from app.ingestion.parsers.base import BaseParser


class CSVParser(BaseParser):
    SUPPORTED_EXTENSIONS = {".csv", ".tsv", ".txt"}

    def supports(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def parse(self, file_path: Path) -> pd.DataFrame:
        try:
            encoding = self._detect_encoding(file_path)
            sep = self._sniff_delimiter(file_path, encoding)
            return pd.read_csv(
                file_path,
                encoding=encoding,
                encoding_errors="replace",
                sep=sep,
                dtype=str,
                keep_default_na=False,
                na_values=["", "NULL", "null", "N/A", "n/a", "NA", "na", "NaN", "nan"],
            )
        except Exception as e:
            raise IngestionError(f"Failed to parse CSV file: {e}") from e

    def _detect_encoding(self, file_path: Path) -> str:
        raw = file_path.read_bytes()[:100_000]
        result = chardet.detect(raw)
        encoding = result.get("encoding") or "utf-8"
        if encoding.lower() == "ascii":
            return "utf-8"
        return encoding

    def _sniff_delimiter(self, file_path: Path, encoding: str) -> str:
        import csv

        with file_path.open(encoding=encoding, errors="replace") as f:
            sample = f.read(4096)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            return dialect.delimiter
        except csv.Error:
            return ","

    def get_schema(self, file_path: Path) -> dict:
        try:
            encoding = self._detect_encoding(file_path)
            sep = self._sniff_delimiter(file_path, encoding)
            df = pd.read_csv(
                file_path,
                encoding=encoding,
                encoding_errors="replace",
                sep=sep,
                nrows=1000,
                keep_default_na=True,
            )
            return {str(col): str(dtype) for col, dtype in df.dtypes.items()}
        except Exception as e:
            raise IngestionError(f"Failed to get schema for CSV file: {e}") from e
