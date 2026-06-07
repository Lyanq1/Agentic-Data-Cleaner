"""Bounded dedup inspection tools."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from langchain_core.tools import tool


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
