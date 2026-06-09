"""Helpers for preserving user-facing dataframe column order."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pandas as pd


def restore_original_column_order(
    dataframe: pd.DataFrame,
    state: Mapping[str, Any],
) -> pd.DataFrame:
    """Order columns like the original uploaded dataset, appending new columns last.

    Lineage rows are stored as PostgreSQL JSONB. JSONB does not preserve object key
    order, so dataframe reconstruction from lineage can shuffle columns unless we
    explicitly restore the source order.
    """
    preferred_columns = _column_order_from_state(state)
    return reorder_columns(dataframe, preferred_columns)


def reorder_columns(
    dataframe: pd.DataFrame,
    preferred_columns: list[str] | None,
) -> pd.DataFrame:
    """Reindex existing columns by preferred order and keep extras at the end."""
    if dataframe.empty or not preferred_columns:
        return dataframe

    preferred_set = set(preferred_columns)
    ordered_existing = [column for column in preferred_columns if column in dataframe.columns]
    extra_columns = [column for column in dataframe.columns if column not in preferred_set]
    if not ordered_existing:
        return dataframe

    return dataframe.loc[:, ordered_existing + extra_columns]


def _column_order_from_state(state: Mapping[str, Any]) -> list[str] | None:
    dataset_path = state.get("dataset_path")
    if isinstance(dataset_path, str) and dataset_path:
        columns = _column_order_from_file(dataset_path)
        if columns:
            return columns

    dataset_schema = state.get("dataset_schema")
    if isinstance(dataset_schema, dict) and dataset_schema:
        return [str(column) for column in dataset_schema.keys()]

    return None


def _column_order_from_file(dataset_path: str) -> list[str] | None:
    path = Path(dataset_path)
    if not path.exists():
        return None

    suffix = path.suffix.lower()
    try:
        if suffix in {".parquet", ".pq"}:
            return [str(column) for column in pd.read_parquet(path).columns]
        if suffix in {".csv", ".txt"}:
            return [str(column) for column in pd.read_csv(path, nrows=0).columns]
        if suffix in {".xlsx", ".xls"}:
            return [str(column) for column in pd.read_excel(path, nrows=0).columns]
        if suffix in {".json", ".jsonl"}:
            return [str(column) for column in pd.read_json(path, lines=suffix == ".jsonl").columns]
    except Exception:
        return None

    return None
