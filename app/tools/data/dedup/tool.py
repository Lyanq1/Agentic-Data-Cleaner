"""Bounded dedup inspection tools."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from langchain_core.tools import tool

from app.agents.deduplication.normalizers import normalize_text


def _read_dataframe(file_path: str) -> pd.DataFrame:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


@tool
def inspect_duplicate_candidates(
    file_path: str,
    candidate_column_sets: list[list[str]],
) -> dict:
    """Inspect duplicate metrics for one or more candidate key column sets."""

    df = _read_dataframe(file_path)
    results: list[dict] = []
    for column_set in candidate_column_sets:
        if not column_set:
            results.append(
                {
                    "column_set": [],
                    "duplicate_count": 0,
                    "duplicate_group_count": 0,
                    "row_count": int(len(df)),
                    "valid": False,
                    "reason": "empty_column_set",
                }
            )
            continue
        missing = [column for column in column_set if column not in df.columns]
        if missing:
            results.append(
                {
                    "column_set": column_set,
                    "duplicate_count": 0,
                    "duplicate_group_count": 0,
                    "row_count": int(len(df)),
                    "valid": False,
                    "reason": f"missing_columns={missing}",
                }
            )
            continue

        duplicate_mask = df.duplicated(subset=column_set, keep=False)
        duplicate_count = int(df.duplicated(subset=column_set, keep="first").sum())
        group_sizes = df.loc[duplicate_mask].groupby(column_set, dropna=False).size()
        duplicate_group_count = int(group_sizes[group_sizes > 1].shape[0])
        results.append(
            {
                "column_set": column_set,
                "duplicate_count": duplicate_count,
                "duplicate_group_count": duplicate_group_count,
                "row_count": int(len(df)),
                "valid": True,
                "reason": None,
            }
        )

    return {"results": results}


@tool
def profile_fuzzy_columns(
    file_path: str,
    candidate_columns: list[str],
) -> dict:
    """Profile candidate fuzzy-blocking columns using the actual dataset."""

    df = _read_dataframe(file_path)
    results: list[dict] = []
    for column in candidate_columns:
        if column not in df.columns:
            results.append(
                {
                    "column": column,
                    "valid": False,
                    "reason": "missing_column",
                }
            )
            continue

        series = df[column]
        non_null = series.dropna()
        normalized = non_null.map(normalize_text)
        normalized = normalized[normalized.astype(str).str.len() > 0]

        row_count = int(len(df))
        non_null_count = int(non_null.shape[0])
        distinct_count = int(normalized.nunique()) if not normalized.empty else 0
        distinct_ratio = float(distinct_count / row_count) if row_count else 0.0
        top_values = (
            normalized.value_counts().head(5).index.tolist()
            if not normalized.empty
            else []
        )
        avg_length = (
            float(normalized.map(len).mean())
            if not normalized.empty
            else 0.0
        )

        results.append(
            {
                "column": column,
                "valid": True,
                "row_count": row_count,
                "non_null_count": non_null_count,
                "non_null_rate": float(non_null_count / row_count) if row_count else 0.0,
                "distinct_count": distinct_count,
                "distinct_ratio": distinct_ratio,
                "average_normalized_length": avg_length,
                "top_normalized_values": top_values,
            }
        )

    return {"results": results}
