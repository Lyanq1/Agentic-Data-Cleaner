"""Exact full-row deduplication."""

from __future__ import annotations

from collections import Counter

import pandas as pd


def execute_full_row_dedup(df: pd.DataFrame) -> dict[str, object]:
    """Remove exact full-row duplicates while collecting metrics."""

    before_row_count = len(df)
    duplicate_mask = df.duplicated(keep=False)
    duplicated_rows = df.loc[duplicate_mask]

    duplicate_groups = 0
    if not duplicated_rows.empty:
        row_tuples = duplicated_rows.astype(object).where(~duplicated_rows.isna(), None)
        counts = Counter(tuple(row) for row in row_tuples.to_numpy().tolist())
        duplicate_groups = sum(1 for count in counts.values() if count > 1)

    deduped_df = df.drop_duplicates(keep="first")
    return {
        "deduped_df": deduped_df,
        "before_row_count": before_row_count,
        "after_row_count": len(deduped_df),
        "full_row_duplicate_count": before_row_count - len(deduped_df),
        "duplicate_group_count": duplicate_groups,
    }
