from pydantic import BaseModel, Field
from typing import Any


class ColumnStatProfile(BaseModel):
    column_name: str
    dtype: str
    null_count: int
    null_rate: float
    unique_count: int
    unique_ratio: float
    sample_values: list[Any] = Field(default_factory=list)
    detected_patterns: list[str] = Field(default_factory=list)
    interpretation: list[str] = Field(default_factory=list)
    numeric_stats: dict[str, Any] | None = None
    categorical_stats: dict[str, Any] | None = None


class StatisticalProfile(BaseModel):
    source: str
    total_rows: int
    total_columns: int
    pk_candidates: list[str] = Field(default_factory=list)
    near_unique_columns: list[str] = Field(default_factory=list)
    categorical_columns: list[str] = Field(default_factory=list)
    high_null_columns: list[str] = Field(default_factory=list)
    duplicate_rows: int = 0
    columns: list[ColumnStatProfile] = Field(default_factory=list)
