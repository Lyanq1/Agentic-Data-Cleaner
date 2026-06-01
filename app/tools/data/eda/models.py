from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any

class UniqueRatioCategory(str, Enum):
    """Semantic label for the unique_ratio value of a column."""

    PRIMARY_KEY    = "primary_key"        # == 1.0 --> every value is distinct
    NEAR_UNIQUE    = "near_unique"        # (0.8, 1.0) --> likely PK with duplicates
    REGULAR        = "regular"            # (0.2, 0.8) --> ordinary column
    CATEGORICAL    = "categorical"        # (0.0, 0.2] --> low-cardinality / categorical
    CONSTANT       = "constant"           # == 0.0 --> single distinct value


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
    duplicate_rows: int = 0

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
            "duplicate_rows": self.duplicate_rows,
            "columns": [c.to_dict() for c in self.columns],
        }
