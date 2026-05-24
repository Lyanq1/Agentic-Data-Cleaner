"""Excel parser — supports .xlsx and .xls, reads first sheet by default."""

from pathlib import Path

import pandas as pd

from app.core.exceptions import IngestionError
from app.services.file.base import BaseParser


class ExcelParser(BaseParser):
    SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".xlsm"}

    def supports(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def parse(self, file_path: Path) -> pd.DataFrame:
        try:
            xf = pd.ExcelFile(file_path)
            # TODO: future — allow user to select sheet via requirements
            sheet = xf.sheet_names[0]
            return xf.parse(
                sheet,
                dtype=str,
                keep_default_na=False,
                na_values=["", "NULL", "null", "N/A", "n/a", "NA", "na", "NaN", "nan"],
            )
        except Exception as e:
            raise IngestionError(f"Failed to parse Excel file: {e}") from e
