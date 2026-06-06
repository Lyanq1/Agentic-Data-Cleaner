from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, List, Dict

@dataclass
class ColumnQuality:
    """Quality profile for a single DataFrame column."""
    column_name: str
    dtype: str
    
    # Null metrics
    null_count: int
    total_rows: int
    null_rate: float
    
    # Duplicate/Uniqueness
    unique_count: int
    unique_ratio: float
    
    # Disguised nulls detection
    disguised_nulls: Dict[str, int] = field(default_factory=dict)
    
    # String patterns (if any)
    detected_patterns: List[str] = field(default_factory=list)
    
    # Quality Issues (Warnings/Errors)
    issues: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class QualityReport:
    """Aggregated Quality Report for the entire dataset."""
    source: str
    total_rows: int
    total_columns: int
    
    # Dataset-level quality checks
    duplicate_rows: int = 0
    passed: bool = True
    
    columns: List[ColumnQuality] = field(default_factory=list)
    
    # Summary of problematic columns
    columns_with_nulls: List[str] = field(default_factory=list)
    columns_with_disguised_nulls: List[str] = field(default_factory=list)
    constant_columns: List[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "total_rows": self.total_rows,
            "total_columns": self.total_columns,
            "duplicate_rows": self.duplicate_rows,
            "passed": self.passed,
            "columns_with_nulls": self.columns_with_nulls,
            "columns_with_disguised_nulls": self.columns_with_disguised_nulls,
            "constant_columns": self.constant_columns,
            "columns": [c.to_dict() for c in self.columns],
        }
