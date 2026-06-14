"""Composite-key deduplication with normalization and weak-key protection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from app.agents.deduplication.column_roles import infer_column_role
from app.agents.deduplication.normalizers import normalize_email, normalize_phone
from app.graphs.states.profiler_state import StatisticalProfile
from app.graphs.states.profiles import SemanticProfile


def _normalize_key_series(
    column_name: str,
    series: pd.Series,
    *,
    explicit_roles: dict[str, str] | None = None,
    semantic_profile: SemanticProfile | None = None,
) -> tuple[pd.Series, bool]:
    role = infer_column_role(
        column_name,
        explicit_roles=explicit_roles,
        semantic_profile=semantic_profile,
    )
    if role == "phone":
        normalized = series.map(normalize_phone)
        return normalized.where(normalized.notna(), series.astype(str)), True
    if role == "email":
        normalized = series.map(normalize_email)
        return normalized.where(normalized.notna(), series.astype(str)), True
    return series.astype(str), False


def _count_duplicate_groups(df: pd.DataFrame, key_columns: list[str]) -> int:
    if not key_columns:
        return 0
    sizes = df.groupby(key_columns, dropna=False).size()
    return int(sizes[sizes > 1].shape[0])


def build_normalized_key_frame(
    df: pd.DataFrame,
    key_columns: list[str],
    *,
    explicit_roles: dict[str, str] | None = None,
    semantic_profile: SemanticProfile | None = None,
) -> pd.DataFrame:
    """Build a normalized comparison frame for the requested key columns."""

    working = df.copy()
    compare_columns: list[str] = []
    for column in key_columns:
        compare_name = f"__dedup_key__{column}"
        normalized_series, _ = _normalize_key_series(
            column,
            working[column],
            explicit_roles=explicit_roles,
            semantic_profile=semantic_profile,
        )
        working[compare_name] = normalized_series.fillna("")
        compare_columns.append(compare_name)
    return working[compare_columns]


@dataclass(slots=True)
class ExactKeyDedupConfig:
    """Execution policy for exact key dedup."""

    key_columns: list[str]
    column_roles: dict[str, str] = field(default_factory=dict)
    semantic_profile: SemanticProfile | None = None
    statistical_profile: StatisticalProfile | None = None
    keep_rule: str = "keep_most_complete"
    notes: list[str] = field(default_factory=list)
    unresolved_collisions: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class CompositeKeyExecutionResult:
    """Result of exact key dedup."""

    deduped_df: pd.DataFrame
    key_duplicate_count: int
    duplicate_group_count: int
    kept_strategy: str
    notes: list[str]
    unresolved_collisions: list[dict[str, Any]]


def execute_exact_key_dedup(df: pd.DataFrame, config: ExactKeyDedupConfig) -> CompositeKeyExecutionResult:
    """Run exact key dedup using normalized comparison columns and keep-most-complete."""

    working = df.copy()
    compare_columns: list[str] = []
    normalized_notes: list[str] = []
    for column in config.key_columns:
        compare_name = f"__dedup_key__{column}"
        normalized_series, changed = _normalize_key_series(
            column,
            working[column],
            explicit_roles=config.column_roles,
            semantic_profile=config.semantic_profile,
        )
        working[compare_name] = normalized_series.fillna("")
        compare_columns.append(compare_name)
        if changed:
            normalized_notes.append(f"Normalized comparison values for key column '{column}'.")

    duplicate_mask = working.duplicated(subset=compare_columns, keep=False)
    key_duplicate_count = int(working.duplicated(subset=compare_columns, keep="first").sum())
    duplicate_group_count = _count_duplicate_groups(working.loc[duplicate_mask], compare_columns)

    if key_duplicate_count == 0:
        return CompositeKeyExecutionResult(
            deduped_df=df,
            key_duplicate_count=0,
            duplicate_group_count=0,
            kept_strategy=config.keep_rule if config.keep_rule in {"keep_first", "keep_last", "keep_most_complete"} else "keep_first",
            notes=normalized_notes,
            unresolved_collisions=list(config.unresolved_collisions),
        )

    keep_rule = config.keep_rule if config.keep_rule in {"keep_first", "keep_last", "keep_most_complete"} else "keep_most_complete"
    working["__null_score__"] = working.isna().sum(axis=1)
    working["__stable_order__"] = range(len(working))
    if keep_rule == "keep_first":
        working["__selection_order__"] = working["__stable_order__"]
        ranked = working.sort_values(compare_columns + ["__selection_order__"], kind="stable")
    elif keep_rule == "keep_last":
        working["__selection_order__"] = -working["__stable_order__"]
        ranked = working.sort_values(compare_columns + ["__selection_order__"], kind="stable")
    else:
        working["__selection_order__"] = working["__stable_order__"]
        ranked = working.sort_values(
            compare_columns + ["__null_score__", "__selection_order__"],
            kind="stable",
        )

    keep_mask = ~ranked.duplicated(subset=compare_columns, keep="first")
    kept = ranked.loc[keep_mask].sort_values("__stable_order__", kind="stable")

    drop_columns = compare_columns + ["__null_score__", "__stable_order__", "__selection_order__"]
    return CompositeKeyExecutionResult(
        deduped_df=kept.drop(columns=drop_columns, errors="ignore"),
        key_duplicate_count=key_duplicate_count,
        duplicate_group_count=duplicate_group_count,
        kept_strategy=keep_rule,
        notes=normalized_notes,
        unresolved_collisions=list(config.unresolved_collisions),
    )


def has_normalized_key_duplicates(
    df: pd.DataFrame,
    key_columns: list[str],
    *,
    explicit_roles: dict[str, str] | None = None,
    semantic_profile: SemanticProfile | None = None,
) -> bool:
    """Check whether duplicates remain under normalized key comparison semantics."""

    if not key_columns:
        return False
    compare_frame = build_normalized_key_frame(
        df,
        key_columns,
        explicit_roles=explicit_roles,
        semantic_profile=semantic_profile,
    )
    return bool(compare_frame.duplicated(keep=False).any())
