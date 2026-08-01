from pathlib import Path
from typing import Any

import pandas as pd

from app.tools.data.eda.utils import _detect_string_patterns
from app.tools.data.quality_control.models import ColumnQuality, QualityReport

class QualityProfiler:
    """Quality Control profiler to validate datasets."""

    def __init__(
        self,
        null_threshold: float = 0.0,
        string_pattern_threshold: float = 0.7,
        allowed_disguised_values: dict[str, list[Any]] | None = None,
    ) -> None:
        self.null_threshold = null_threshold
        self.string_pattern_threshold = string_pattern_threshold
        self.allowed_disguised_values = {
            column: {str(value).strip().casefold() for value in values}
            for column, values in (allowed_disguised_values or {}).items()
        }

    def check_file(self, file_path: str | Path) -> QualityReport:
        """Load a file (CSV, TSV, Parquet) and return a QualityReport."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
            
        if path.suffix.lower() == ".parquet":
            df = pd.read_parquet(path)
        else:
            raise ValueError(f"Unsupported file format: {path.suffix}")
            
        return self.check_dataframe(df, source=str(path))

    def check_dataframe(self, df: pd.DataFrame, source: str = "<in-memory DataFrame>") -> QualityReport:
        """Profile an in-memory pandas DataFrame and return a QualityReport."""
        total_rows = len(df)
        columns_quality = []
        
        columns_with_nulls = []
        columns_with_disguised_nulls = []
        constant_columns = []

        for col in df.columns:
            col_quality = self._check_column(df, col, total_rows)
            columns_quality.append(col_quality)
            
            if col_quality.null_count > 0:
                columns_with_nulls.append(col)
            if col_quality.disguised_nulls:
                columns_with_disguised_nulls.append(col)
            if col_quality.unique_ratio == 0.0 and total_rows > 0:
                constant_columns.append(col)

        duplicate_rows = int(df.duplicated().sum())
        
        # Determine overall pass/fail status
        # If any column has nulls above threshold, or duplicates exist, or disguised nulls exist, it might fail.
        # We will be strict: any issues across columns will mark passed = False
        passed = True
        if duplicate_rows > 0:
            passed = False
        for c in columns_quality:
            if c.issues:
                passed = False

        return QualityReport(
            source=source,
            total_rows=total_rows,
            total_columns=len(df.columns),
            duplicate_rows=duplicate_rows,
            passed=passed,
            columns=columns_quality,
            columns_with_nulls=columns_with_nulls,
            columns_with_disguised_nulls=columns_with_disguised_nulls,
            constant_columns=constant_columns,
        )

    def _check_column(self, df: pd.DataFrame, col: str, total_rows: int) -> ColumnQuality:
        """Perform quality checks on a single column."""
        series = df[col]
        
        # Map physical Pandas dtypes to semantic/logical types
        import datetime
        dtype_str = str(series.dtype)
        if pd.api.types.is_integer_dtype(series):
            dtype_str = "int"
        elif pd.api.types.is_float_dtype(series):
            dtype_str = "float"
        elif pd.api.types.is_bool_dtype(series) or dtype_str in ("bool", "boolean"):
            dtype_str = "bool"
        elif pd.api.types.is_datetime64_any_dtype(series):
            non_nulls = series.dropna()
            # If all times are 00:00:00, map to date, otherwise datetime
            if not non_nulls.empty and (non_nulls.dt.time == datetime.time(0)).all():
                dtype_str = "date"
            else:
                dtype_str = "datetime"
        elif dtype_str in ("string", "object"):
            # Check if it contains time objects or ISO time strings
            non_nulls = series.dropna()
            if not non_nulls.empty:
                # 1. Native datetime.time objects (e.g., from Parquet)
                if non_nulls.apply(lambda x: isinstance(x, datetime.time)).all():
                    dtype_str = "time"
                else:
                    # 2. String representations of ISO time (e.g., from CSV)
                    # Matches HH:MM or HH:MM:SS or HH:MM:SS.mmmmmm (24-hour format)
                    time_pattern = r"^([01]?\d|2[0-3]):([0-5]\d)(:([0-5]\d)(\.\d+)?)?$"
                    if non_nulls.apply(lambda x: isinstance(x, str)).all():
                        if non_nulls.astype(str).str.strip().str.match(time_pattern).all():
                            dtype_str = "time"
                        else:
                            dtype_str = "str"
                    else:
                        dtype_str = "str"
            else:
                dtype_str = "str"
        else:
            dtype_str = "str"

        # 1. Null metrics
        null_count = int(series.isna().sum())
        null_rate  = null_count / total_rows if total_rows > 0 else 0.0

        # 2. Unique metrics
        unique_count = int(series.nunique(dropna=True))
        unique_ratio = unique_count / total_rows if total_rows > 0 else 0.0

        issues = []
        if null_rate > self.null_threshold:
            issues.append(f"Null rate {null_rate:.2%} exceeds threshold {self.null_threshold:.2%}")
            
        if unique_ratio == 0.0 and total_rows > 0:
            issues.append("Column is constant (only 1 distinct value)")

        # 3. Disguised nulls detection
        detected_disguised_nulls = {}
        is_numeric = (
            pd.api.types.is_numeric_dtype(series)
            and not pd.api.types.is_bool_dtype(series)
            and not isinstance(series.dtype, pd.CategoricalDtype)
        )
        if not is_numeric:
            disguised_null_rules = ["n/a", "null", "unknown", "-", "none", "0", ""]
            raw_str_series = series.dropna().astype(str).str.strip()
            str_series = raw_str_series.str.casefold()
            allowed_mask = str_series.isin(
                self.allowed_disguised_values.get(str(col), set())
            )
            for rule in disguised_null_rules:
                count = int(((str_series == rule) & ~allowed_mask).sum())
                if count > 0:
                    detected_disguised_nulls[rule] = count
                    
        if detected_disguised_nulls:
            issues.append(f"Disguised nulls detected: {detected_disguised_nulls}")

        # 4. String pattern detection (to flag mixed data)
        detected_patterns = []
        is_string_like = (
            pd.api.types.is_object_dtype(series)
            or pd.api.types.is_string_dtype(series)
        )
        if is_string_like:
            non_null_samples = series.dropna().head(100).astype(str).tolist()
            if non_null_samples:
                detected_patterns = _detect_string_patterns(
                    non_null_samples, threshold=self.string_pattern_threshold
                )

        return ColumnQuality(
            column_name=col,
            dtype=dtype_str,
            null_count=null_count,
            total_rows=total_rows,
            null_rate=null_rate,
            unique_count=unique_count,
            unique_ratio=round(unique_ratio, 6),
            disguised_nulls=detected_disguised_nulls,
            detected_patterns=detected_patterns,
            issues=issues
        )
