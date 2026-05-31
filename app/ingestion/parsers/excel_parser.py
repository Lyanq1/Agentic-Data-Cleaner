"""Excel parser — supports .xlsx and .xls, reads first sheet by default."""
from pathlib import Path

import pandas as pd

from app.exceptions.ingestion_exceptions import IngestionError
from app.ingestion.parsers.base import BaseParser


class ExcelParser(BaseParser):
    SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".xlsm"}

    def supports(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def parse(self, file_path: Path) -> pd.DataFrame:
        try:
            xf = pd.ExcelFile(file_path)
            sheet = xf.sheet_names[0]
            return xf.parse(
                sheet,
                dtype=str,
                keep_default_na=False,
                na_values=["", "NULL", "null", "N/A", "n/a", "NA", "na", "NaN", "nan"],
            )
        except Exception as e:
            raise IngestionError(f"Failed to parse Excel file: {e}") from e

    def get_schema(self, file_path: Path) -> dict:
        try:
            xf = pd.ExcelFile(file_path)
            sheet = xf.sheet_names[0]
            df = xf.parse(
                sheet,
                nrows=1000,
                keep_default_na=True,
            )
            return {str(col): str(dtype) for col, dtype in df.dtypes.items()}
        except Exception as e:
            raise IngestionError(f"Failed to get schema for Excel file: {e}") from e
