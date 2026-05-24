"""Statistical Profiler — EDA phase: per-column statistical profiling.

Computes the following metrics for each column in a DataFrame / Parquet file:

1. **Null rate**        : null_count / total_rows  (tỷ lệ null theo cột)
2. **Sample values**   : representative non-null sample (top-freq + random mix)
3. **Unique ratio**    : unique_count / total_rows  — used to identify PK candidates:
       • unique_ratio == 1.0        --> likely Primary Key / ID column
       • unique_ratio ≈ 1.0 < 1.0  --> has duplicates in this column — investigate
       • unique_ratio in (0.0–0.2)  --> categorical column (gender, status, type…)
       • unique_ratio in (0.2–0.8)  --> regular column (not key, not purely categorical)
4. **Current dtype**   : pandas dtype of the column as stored
5. **String patterns** : regex patterns detected from string samples (email, phone,
                         date, URL, UUID, zip-code, integer string, float string…)

Usage
-----
::

    from app.tools.data_profiler.statistical_profiler import StatisticalProfiler

    profiler = StatisticalProfiler()

    # From a Parquet file
    report = profiler.profile_parquet("path/to/file.parquet")

    # From an in-memory DataFrame
    report = profiler.profile_dataframe(df)

    # Pretty-print to console
    profiler.print_report(report)

    # Convert to dict / JSON
    data = report.to_dict()

The ``ColumnStat`` and ``StatisticalReport`` dataclasses are also importable
for type-hinted downstream usage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any

import pandas as pd
import numpy as np
from langchain_core.tools import tool

class UniqueRatioCategory(str, Enum):
    """Semantic label for the unique_ratio value of a column."""

    PRIMARY_KEY    = "primary_key"        # == 1.0 --> every value is distinct
    NEAR_UNIQUE    = "near_unique"        # (0.8, 1.0) --> likely PK with duplicates
    REGULAR        = "regular"            # (0.2, 0.8) --> ordinary column
    CATEGORICAL    = "categorical"        # (0.0, 0.2] --> low-cardinality / categorical
    CONSTANT       = "constant"           # == 0.0 --> single distinct value


def _categorise_unique_ratio(ratio: float) -> UniqueRatioCategory:
    """Map a numeric unique_ratio to its semantic UniqueRatioCategory."""
    if ratio == 1.0:
        return UniqueRatioCategory.PRIMARY_KEY
    if ratio > 0.8:
        return UniqueRatioCategory.NEAR_UNIQUE
    if ratio > 0.2:
        return UniqueRatioCategory.REGULAR
    if ratio > 0.0:
        return UniqueRatioCategory.CATEGORICAL
    return UniqueRatioCategory.CONSTANT


# String-pattern detection

# (pattern_name, compiled_regex, min_match_fraction_to_report)
_STRING_PATTERNS: list[tuple[str, re.Pattern[str], float]] = [
    ("uuid",         re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"), 0.8),
    ("email",        re.compile(r"^[\w.+\-]+@[\w\-]+\.[a-zA-Z]{2,}$"), 0.8),
    ("url",          re.compile(r"^https?://\S+"), 0.8),
    ("date_iso",     re.compile(r"^\d{4}-\d{2}-\d{2}$"), 0.8),
    ("datetime_iso", re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}"), 0.8),
    ("phone",        re.compile(r"^\+?[\d\s\-(]{7,20}$"), 0.7),
    ("zip_us",       re.compile(r"^\d{5}(-\d{4})?$"), 0.8),
    ("integer_str",  re.compile(r"^-?\d+$"), 0.8),
    ("float_str",    re.compile(r"^-?\d+\.\d+$"), 0.8),
    ("boolean_str",  re.compile(r"^(true|false|yes|no|1|0)$", re.IGNORECASE), 0.9),
    ("json_object",  re.compile(r"^\s*\{.*\}\s*$", re.DOTALL), 0.7),
    ("json_array",   re.compile(r"^\s*\[.*\]\s*$", re.DOTALL), 0.7),
]


def _detect_string_patterns(samples: list[str], threshold: float = 0.7) -> list[str]:
    """Return pattern names that match at least *threshold* fraction of *samples*.

    Only non-null string samples should be passed in.  A pattern is included
    if ``matched_count / len(samples) >= threshold``.
    """
    if not samples:
        return []

    detected: list[str] = []
    n = len(samples)
    for pattern_name, regex, min_frac in _STRING_PATTERNS:
        matched = sum(1 for s in samples if regex.fullmatch(s) is not None)
        if matched / n >= min(threshold, min_frac):
            detected.append(pattern_name)
            break  # Take only the first (most specific) match to avoid over-tagging

    # If nothing matched yet, fall back to any pattern above the user threshold
    if not detected:
        for pattern_name, regex, _min_frac in _STRING_PATTERNS:
            matched = sum(1 for s in samples if regex.fullmatch(s) is not None)
            if matched / n >= threshold:
                detected.append(pattern_name)

    return detected


# Per-column result dataclass

@dataclass
class ColumnStat:
    """Statistical profile for a single DataFrame column."""

    # Identity
    column_name: str
    dtype: str                          # pandas dtype string (e.g. "object", "int64")

    # Null metrics
    null_count: int
    total_rows: int
    null_rate: float                    # null_count / total_rows  ∈ [0, 1]

    # Uniqueness metrics
    unique_count: int
    unique_ratio: float                 # unique_count / total_rows  ∈ [0, 1]
    unique_ratio_category: UniqueRatioCategory

    # Representative sample (non-null values)
    sample_values: list[Any] = field(default_factory=list)

    # String pattern (only populated when dtype is object/string)
    detected_patterns: list[str] = field(default_factory=list)

    # Human-readable interpretation messages
    interpretation: list[str] = field(default_factory=list)

    # Detailed stats for UI visualization
    numeric_stats: dict[str, Any] | None = None
    categorical_stats: dict[str, Any] | None = None

    # Convenience properties

    @property
    def non_null_count(self) -> int:
        return self.total_rows - self.null_count

    @property
    def is_pk_candidate(self) -> bool:
        return self.unique_ratio_category == UniqueRatioCategory.PRIMARY_KEY

    @property
    def is_categorical(self) -> bool:
        return self.unique_ratio_category == UniqueRatioCategory.CATEGORICAL

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["unique_ratio_category"] = self.unique_ratio_category.value
        return d


# Full report dataclass

@dataclass
class StatisticalReport:
    """Aggregated EDA statistical report for an entire dataset."""

    source: str                             # File path or label
    total_rows: int
    total_columns: int
    columns: list[ColumnStat] = field(default_factory=list)

    # Dataset-level summary
    pk_candidates: list[str] = field(default_factory=list)
    near_unique_columns: list[str] = field(default_factory=list)
    categorical_columns: list[str] = field(default_factory=list)
    high_null_columns: list[str] = field(default_factory=list)   # null_rate > 0.5

    def get_column(self, name: str) -> ColumnStat | None:
        return next((c for c in self.columns if c.column_name == name), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "total_rows": self.total_rows,
            "total_columns": self.total_columns,
            "pk_candidates": self.pk_candidates,
            "near_unique_columns": self.near_unique_columns,
            "categorical_columns": self.categorical_columns,
            "high_null_columns": self.high_null_columns,
            "columns": [c.to_dict() for c in self.columns],
        }


# Main profiler class

class StatisticalProfiler:
    """Compute EDA statistical profiles for every column in a dataset.

    Parameters
    ----------
    sample_size : int
        Maximum number of representative sample values to collect per column.
        The sample is built by mixing the top-frequency values with random draws
        to avoid head-of-file bias (same strategy as DataProfiler).
    string_pattern_threshold : float
        Fraction of non-null string samples that must match a regex pattern for
        it to be reported as detected (default 0.7 = 70 %).
    high_null_threshold : float
        Columns whose null_rate exceeds this value are flagged in the dataset-level
        ``high_null_columns`` summary (default 0.5 = 50 %).
    """

    def __init__(
        self,
        sample_size: int = 20,
        string_pattern_threshold: float = 0.7,
        high_null_threshold: float = 0.5,
    ) -> None:
        self.sample_size = sample_size
        self.string_pattern_threshold = string_pattern_threshold
        self.high_null_threshold = high_null_threshold

    # Public API

    def profile_parquet(self, parquet_path: str | Path) -> StatisticalReport:
        """Load a Parquet file and return a full StatisticalReport."""
        path = Path(parquet_path)
        if not path.exists():
            raise FileNotFoundError(f"Parquet file not found: {parquet_path}")
        df = pd.read_parquet(path)
        return self.profile_dataframe(df, source=str(path))

    def profile_dataframe(
        self,
        df: pd.DataFrame,
        source: str = "<in-memory DataFrame>",
    ) -> StatisticalReport:
        """Profile an in-memory pandas DataFrame and return a StatisticalReport."""
        total_rows = len(df)
        column_stats = [self._profile_column(df, col, total_rows) for col in df.columns]

        pk_candidates     = [c.column_name for c in column_stats if c.unique_ratio_category == UniqueRatioCategory.PRIMARY_KEY]
        near_unique       = [c.column_name for c in column_stats if c.unique_ratio_category == UniqueRatioCategory.NEAR_UNIQUE]
        categorical       = [c.column_name for c in column_stats if c.is_categorical]
        high_null         = [c.column_name for c in column_stats if c.null_rate > self.high_null_threshold]

        return StatisticalReport(
            source=source,
            total_rows=total_rows,
            total_columns=len(df.columns),
            columns=column_stats,
            pk_candidates=pk_candidates,
            near_unique_columns=near_unique,
            categorical_columns=categorical,
            high_null_columns=high_null,
        )

    def print_report(self, report: StatisticalReport, *, max_samples: int = 8) -> None:
        """Pretty-print a StatisticalReport to stdout using plain text formatting.

        This method has no external dependencies (no rich, no tabulate) so it
        works in any environment.
        """
        sep_major = "=" * 80
        sep_minor = "-" * 80

        print(sep_major)
        print(f"  EDA STATISTICAL PROFILE")
        print(f"  Source       : {report.source}")
        print(f"  Total rows   : {report.total_rows:,}")
        print(f"  Total columns: {report.total_columns}")
        print(sep_major)

        # Dataset-level highlights
        if report.pk_candidates:
            print(f"\n  🔑 PK Candidates (unique_ratio = 1.0): {report.pk_candidates}")
        if report.near_unique_columns:
            print(f"  ⚠️  Near-unique (duplicates detected) : {report.near_unique_columns}")
        if report.categorical_columns:
            print(f"  🏷️  Categorical columns                : {report.categorical_columns}")
        if report.high_null_columns:
            print(f"  🚨 High-null columns (> {self.high_null_threshold:.0%})        : {report.high_null_columns}")

        print()

        # Per-column table
        for stat in report.columns:
            print(sep_minor)
            print(f"  Column : {stat.column_name!r}")
            print(f"  dtype  : {stat.dtype}")
            print(f"  Nulls  : {stat.null_count:,} / {stat.total_rows:,}  ({stat.null_rate:.2%})")
            print(
                f"  Unique : {stat.unique_count:,} distinct values  "
                f"(unique_ratio = {stat.unique_ratio:.4f}  --> {stat.unique_ratio_category.value})"
            )

            if stat.detected_patterns:
                print(f"  Patterns detected: {stat.detected_patterns}")

            samples_display = stat.sample_values[:max_samples]
            truncated = len(stat.sample_values) > max_samples
            samples_str = repr(samples_display)
            if truncated:
                samples_str += f"  … (+{len(stat.sample_values) - max_samples} more)"
            print(f"  Sample values: {samples_str}")

            for msg in stat.interpretation:
                print(f"    ℹ️  {msg}")

        print(sep_major)

    # Internal helpers
    def _profile_column(self, df: pd.DataFrame, col: str, total_rows: int) -> ColumnStat:
        """Compute all metrics for a single column."""
        series = df[col]
        dtype_str = str(series.dtype)

        # 1. Null metrics
        null_count = int(series.isna().sum())
        null_rate  = null_count / total_rows if total_rows > 0 else 0.0

        # 2. Unique metrics
        unique_count = int(series.nunique(dropna=True))
        unique_ratio = unique_count / total_rows if total_rows > 0 else 0.0
        unique_category = _categorise_unique_ratio(unique_ratio)

        # 3. Sample values
        sample_values = self._representative_sample(series, n=self.sample_size)

        # 4. String pattern detection
        detected_patterns: list[str] = []
        is_string_like = (
            pd.api.types.is_object_dtype(series)
            or pd.api.types.is_string_dtype(series)
        )
        if is_string_like and sample_values:
            str_samples = [str(v) for v in sample_values if v is not None]
            if str_samples:
                detected_patterns = _detect_string_patterns(
                    str_samples, threshold=self.string_pattern_threshold
                )

        # 5. Human-readable interpretation
        interpretation = self._interpret(
            null_rate=null_rate,
            unique_ratio=unique_ratio,
            unique_category=unique_category,
            unique_count=unique_count,
            total_rows=total_rows,
            detected_patterns=detected_patterns,
            dtype_str=dtype_str,
        )

        # 6. Compute Detailed Numerical / Categorical Statistics
        is_numeric = (
            pd.api.types.is_numeric_dtype(series)
            and not pd.api.types.is_bool_dtype(series)
            and not isinstance(series.dtype, pd.CategoricalDtype)
        )

        numeric_stats = None
        categorical_stats = None
        non_null = series.dropna()

        if is_numeric and len(non_null) > 0:
            try:
                v_max = float(non_null.max())
                v_min = float(non_null.min())
                v_mean = float(non_null.mean())
                v_median = float(non_null.median())
                p95 = float(non_null.quantile(0.95))
                q3 = float(non_null.quantile(0.75))
                q1 = float(non_null.quantile(0.25))
                p5 = float(non_null.quantile(0.05))
                
                v_range = v_max - v_min
                v_iqr = q3 - q1
                v_std = float(non_null.std()) if len(non_null) > 1 else 0.0
                v_var = float(non_null.var()) if len(non_null) > 1 else 0.0
                v_kurt = float(non_null.kurt()) if len(non_null) > 1 else 0.0
                v_skew = float(non_null.skew()) if len(non_null) > 1 else 0.0
                v_sum = float(non_null.sum())
                
                zero_count = int((series == 0).sum())
                zero_pct = round(zero_count / total_rows, 4) if total_rows > 0 else 0.0

                # Compute histogram
                counts, bin_edges = np.histogram(non_null, bins=10)
                histogram = []
                for i in range(len(counts)):
                    histogram.append({
                        "bin_start": float(bin_edges[i]),
                        "bin_end": float(bin_edges[i+1]),
                        "count": int(counts[i])
                    })

                numeric_stats = {
                    "values_count": len(non_null),
                    "values_pct": round(len(non_null) / total_rows, 4) if total_rows > 0 else 0.0,
                    "missing_count": null_count,
                    "missing_pct": round(null_rate, 4),
                    "distinct_count": unique_count,
                    "distinct_pct": round(unique_ratio, 4),
                    "zeroes_count": zero_count,
                    "zeroes_pct": zero_pct,
                    "max": v_max,
                    "p95": p95,
                    "q3": q3,
                    "median": v_median,
                    "avg": v_mean,
                    "q1": q1,
                    "p5": p5,
                    "min": v_min,
                    "range": v_range,
                    "iqr": v_iqr,
                    "std": v_std,
                    "var": v_var,
                    "kurt": v_kurt,
                    "skew": v_skew,
                    "sum": v_sum,
                    "histogram": histogram
                }
            except Exception:
                pass

        if numeric_stats is None:
            # Fallback or main logic for Categorical
            try:
                freq = series.value_counts(dropna=True).head(5)
                frequencies = []
                for val, count in freq.items():
                    frequencies.append({
                        "value": str(val),
                        "count": int(count),
                        "pct": round(float(count / total_rows), 4) if total_rows > 0 else 0.0
                    })
                
                total_freq_count = sum(f["count"] for f in frequencies)
                other_count = len(non_null) - total_freq_count
                if other_count > 0:
                    frequencies.append({
                        "value": "(Other)",
                        "count": int(other_count),
                        "pct": round(float(other_count / total_rows), 4) if total_rows > 0 else 0.0
                    })

                categorical_stats = {
                    "values_count": len(non_null),
                    "values_pct": round(len(non_null) / total_rows, 4) if total_rows > 0 else 0.0,
                    "missing_count": null_count,
                    "missing_pct": round(null_rate, 4),
                    "distinct_count": unique_count,
                    "distinct_pct": round(unique_ratio, 4),
                    "frequencies": frequencies
                }
            except Exception:
                pass

        return ColumnStat(
            column_name=col,
            dtype=dtype_str,
            null_count=null_count,
            total_rows=total_rows,
            null_rate=null_rate,
            unique_count=unique_count,
            unique_ratio=round(unique_ratio, 6),
            unique_ratio_category=unique_category,
            sample_values=sample_values,
            detected_patterns=detected_patterns,
            interpretation=interpretation,
            numeric_stats=numeric_stats,
            categorical_stats=categorical_stats,
        )

    @staticmethod
    def _representative_sample(series: pd.Series, n: int = 20) -> list[Any]:
        """Return a sample mixing top-frequency values and random draws.

        Strategy mirrors DataProfiler._representative_sample to keep
        cross-tool consistency:
          1. Top-(n//2) most frequent unique values  --> dominant patterns.
          2. Random draw from remaining values        --> catches rare anomalies.
          3. Deduplicate and cap at *n*.
        """
        non_null = series.dropna()
        if non_null.empty:
            return []

        # Operate on a bounded sub-sample to keep value_counts fast
        work = non_null.sample(n=50_000, random_state=42) if len(non_null) > 50_000 else non_null

        top_freq = work.value_counts().head(n // 2).index.tolist()

        pool = non_null.sample(n=min(1_000, len(non_null)), random_state=42)
        remaining = pool[~pool.isin(top_freq)]
        random_count = min(n - len(top_freq), len(remaining))
        random_vals = remaining.head(random_count).tolist() if random_count > 0 else []

        combined = list(dict.fromkeys(top_freq + random_vals))
        return combined[:n]

    @staticmethod
    def _interpret(
        *,
        null_rate: float,
        unique_ratio: float,
        unique_category: UniqueRatioCategory,
        unique_count: int,
        total_rows: int,
        detected_patterns: list[str],
        dtype_str: str,
    ) -> list[str]:
        """Generate human-readable interpretation messages for a column."""
        msgs: list[str] = []

        # Null interpretation
        if null_rate == 0.0:
            msgs.append("No missing values — column is complete.")
        elif null_rate <= 0.05:
            msgs.append(f"Very low null rate ({null_rate:.2%}) — acceptable for most pipelines.")
        elif null_rate <= 0.20:
            msgs.append(f"Moderate null rate ({null_rate:.2%}) — consider imputation strategy.")
        elif null_rate <= 0.50:
            msgs.append(f"High null rate ({null_rate:.2%}) — column may need significant imputation or removal.")
        else:
            msgs.append(f"Critical null rate ({null_rate:.2%}) — column is mostly empty, evaluate dropping it.")

        # Unique-ratio interpretation
        if unique_category == UniqueRatioCategory.PRIMARY_KEY:
            msgs.append(
                "unique_ratio = 1.0 --> every row has a distinct value — "
                "strong Primary Key / ID candidate."
            )
        elif unique_category == UniqueRatioCategory.NEAR_UNIQUE:
            msgs.append(
                f"unique_ratio = {unique_ratio:.4f} (< 1.0) — "
                f"{total_rows - unique_count:,} duplicate value(s) detected — "
                "investigate for unintended duplicates."
            )
        elif unique_category == UniqueRatioCategory.CATEGORICAL:
            msgs.append(
                f"unique_ratio = {unique_ratio:.4f} (low) — "
                f"only {unique_count:,} distinct values --> likely a categorical column "
                "(e.g. gender, status, type)."
            )
        elif unique_category == UniqueRatioCategory.CONSTANT:
            msgs.append(
                "unique_ratio = 0.0 — single constant value across all rows — "
                "column carries no information; consider dropping."
            )
        else:
            msgs.append(
                f"unique_ratio = {unique_ratio:.4f} — regular column "
                "(not a key, not purely categorical)."
            )

        # Pattern interpretation
        if detected_patterns:
            msgs.append(f"String pattern detected: {detected_patterns} — dtype may be refinable.")

        return msgs


@tool
def perform_eda(file_path: str) -> dict:
    """Perform Statistical Profiling EDA on a dataset (CSV, TSV, or Parquet).
    Args:
        file_path: Path to the dataset file (CSV, TSV, or Parquet).

    Returns:
        A dictionary containing the full statistical report (nulls, uniqueness, string patterns, distributions).
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    profiler = StatisticalProfiler()
    if path.suffix.lower() == ".parquet":   
        report = profiler.profile_parquet(path)
    elif path.suffix.lower() in {".csv", ".tsv"}:
        sep = "\t" if path.suffix.lower() == ".tsv" else ","
        df = pd.read_csv(path, sep=sep)
        report = profiler.profile_dataframe(df, source=str(path))
    else:
        raise ValueError(f"Unsupported file format: {path.suffix}")

    return report.to_dict()


# CLI entry-point (python -m ...)
def _cli_main() -> None:  # pragma: no cover
    """Minimal CLI: python -m app.tools.data_profiler.statistical_profiler <path>"""
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python -m app.tools.data_profiler.statistical_profiler <path.parquet|path.csv>")
        sys.exit(1)

    file_path = Path(sys.argv[1])
    profiler = StatisticalProfiler()

    if file_path.suffix.lower() == ".parquet":
        report = profiler.profile_parquet(file_path)
    elif file_path.suffix.lower() in {".csv", ".tsv"}:
        sep = "\t" if file_path.suffix.lower() == ".tsv" else ","
        df = pd.read_csv(file_path, sep=sep)
        report = profiler.profile_dataframe(df, source=str(file_path))
    else:
        print(f"Unsupported file format: {file_path.suffix}")
        sys.exit(1)

    # Pretty-print to terminal
    profiler.print_report(report)

    # Optionally dump JSON if --json flag is passed
    if "--json" in sys.argv:
        print("\n" + json.dumps(report.to_dict(), indent=2, default=str))


if __name__ == "__main__":
    _cli_main()