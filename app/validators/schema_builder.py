"""Build Pandera schemas from planner work orders.

The planner owns *intent* (columns, strategies, verification hints). This module owns
the deterministic mapping from that intent to Pandera checks.
"""

from __future__ import annotations

from typing import Any, cast

import pandera.pandas as pa

from app.graphs.states.global_state import SemanticProfile, TaskDetail

PANDERA_DTYPE_BY_EXPECTED_TYPE: dict[str, Any] = {
    "int": int,
    "integer": int,
    "float": float,
    "number": float,
    "str": str,
    "string": str,
    "bool": bool,
    "boolean": bool,
    "date": pa.DateTime,
    "datetime": pa.DateTime,
}


def build_pandera_schema(
    task: TaskDetail,
    semantic_profile: SemanticProfile | None = None,
) -> pa.DataFrameSchema:
    """Build a task-specific Pandera schema from an execution-plan work order."""
    columns = _base_columns(task, semantic_profile)
    dataframe_checks: list[pa.Check] = []
    unique: list[str] | None = None

    if task.task_id == "deduplication":
        unique = _dedup_unique_columns(task)
        dataframe_checks.extend(_success_metric_checks(task))
    elif task.task_id == "null_handling":
        _apply_null_strategy(columns, task, semantic_profile)
    elif task.task_id == "type_casting":
        _apply_type_strategy(columns, task, semantic_profile)

    dataframe_checks.extend(_verification_checks(task, columns))

    return pa.DataFrameSchema(
        columns=columns,
        checks=dataframe_checks,
        unique=unique,
        strict=False,
        coerce=False,
        name=f"{task.task_id}_post_worker_schema",
    )


def _get_strategy_dict(task: TaskDetail) -> dict[str, Any]:
    val = task.strategy
    if val is None:
        return {}
    if hasattr(val, "model_dump"):
        return cast("dict[str, Any]", val.model_dump())
    if hasattr(val, "dict"):
        return cast("dict[str, Any]", val.dict())
    if isinstance(val, dict):
        return val
    return {}


def _base_columns(
    task: TaskDetail,
    semantic_profile: SemanticProfile | None,
) -> dict[str, pa.Column]:
    """Create required columns from task columns, strategy, verification, and profile hints."""
    column_names = set(task.columns or [])
    strategy = _get_strategy_dict(task)
    per_column = strategy.get("per_column")
    if isinstance(per_column, dict):
        column_names.update(str(col) for col in per_column)

    if task.task_id == "deduplication":
        column_names.update(_dedup_unique_columns(task))

    verification = task.verification
    if verification:
        for check in verification.pandera_checks:
            if isinstance(check, dict):
                col = check.get("column")
            else:
                col = check.column
            if col:
                column_names.add(col)

    semantic_columns = semantic_profile.columns if semantic_profile else {}
    columns: dict[str, pa.Column] = {}
    for column_name in sorted(column_names):
        semantic = semantic_columns.get(column_name)
        nullable = True if semantic is None else semantic.allow_missing
        dtype = _semantic_dtype(column_name, semantic_profile)
        checks = _semantic_checks(column_name, semantic_profile)
        columns[column_name] = pa.Column(dtype, checks=checks, nullable=nullable, required=True)
    return columns


def _dedup_unique_columns(task: TaskDetail) -> list[str]:
    strategy = _get_strategy_dict(task)
    primary_keys = strategy.get("primary_keys")
    if isinstance(primary_keys, list):
        return [str(col) for col in primary_keys if col]
    return []


def _apply_null_strategy(
    columns: dict[str, pa.Column],
    task: TaskDetail,
    semantic_profile: SemanticProfile | None,
) -> None:
    strategy = _get_strategy_dict(task)
    per_column = strategy.get("per_column")
    if not isinstance(per_column, dict):
        return

    for column_name, config in per_column.items():
        column = str(column_name)
        column_config = config if isinstance(config, dict) else {}
        null_strategy = str(column_config.get("strategy", ""))
        dtype = _semantic_dtype(column, semantic_profile)
        checks = _semantic_checks(column, semantic_profile)

        nullable = null_strategy not in {
            "fill_mean",
            "fill_median",
            "fill_mode",
            "fill_value",
            "drop_row",
        }
        columns[column] = pa.Column(dtype, checks=checks, nullable=nullable, required=True)


def _apply_type_strategy(
    columns: dict[str, pa.Column],
    task: TaskDetail,
    semantic_profile: SemanticProfile | None,
) -> None:
    strategy = _get_strategy_dict(task)
    per_column = strategy.get("per_column")
    if not isinstance(per_column, dict):
        return

    for column_name, config in per_column.items():
        column = str(column_name)
        column_config = config if isinstance(config, dict) else {}
        expected_type = str(column_config.get("expected_type", "")).lower()
        dtype = PANDERA_DTYPE_BY_EXPECTED_TYPE.get(expected_type) or _semantic_dtype(
            column,
            semantic_profile,
        )
        nullable = _semantic_nullable(column, semantic_profile)
        checks = _semantic_checks(column, semantic_profile)
        columns[column] = pa.Column(dtype, checks=checks, nullable=nullable, required=True)


def _verification_checks(task: TaskDetail, columns: dict[str, pa.Column]) -> list[pa.Check]:
    verification = task.verification
    if not verification:
        return []

    checks: list[pa.Check] = []
    for check in verification.pandera_checks:
        if isinstance(check, dict):
            rule = check.get("type", "")
            col = check.get("column")
            threshold_val = check.get("threshold")
        else:
            rule = check.type
            col = check.column
            threshold_val = check.threshold

        if rule in ("column_unique", "is_unique") and col:
            if col in columns:
                _set_column_unique(columns, col)
        elif rule in ("null_rate_lt", "null_rate_lte") and col:
            threshold = float(threshold_val if threshold_val is not None else 0.0)
            _add_null_rate_check(columns, col, threshold)
        elif rule in ("dataframe_no_exact_duplicates", "no_duplicate_rows"):
            checks.append(
                pa.Check(
                    lambda df: not bool(df.duplicated().any()),
                    name="no_duplicate_rows",
                )
            )
    return checks


def _success_metric_checks(task: TaskDetail) -> list[pa.Check]:
    verification = task.verification
    if not verification or not verification.success_metrics:
        return []

    checks: list[pa.Check] = []
    duplicate_rows = verification.success_metrics.get("duplicate_rows")
    if duplicate_rows == 0:
        checks.append(
            pa.Check(
                lambda df: int(df.duplicated().sum()) == 0,
                name="duplicate_rows_eq_0",
            )
        )
    return checks


def _add_null_rate_check(
    columns: dict[str, pa.Column],
    column: str,
    threshold: float,
) -> None:
    existing = columns.get(column, pa.Column(required=True))
    checks = _column_checks(existing)
    checks.append(
        pa.Check(
            lambda series, limit=threshold: float(series.isna().mean()) <= limit,
            name=f"null_rate_lte_{threshold}",
        )
    )
    columns[column] = pa.Column(
        existing.dtype,
        checks=checks,
        nullable=existing.nullable,
        required=existing.required,
        unique=existing.unique,
    )


def _set_column_unique(columns: dict[str, pa.Column], column: str) -> None:
    existing = columns[column]
    columns[column] = pa.Column(
        existing.dtype,
        checks=_column_checks(existing),
        nullable=existing.nullable,
        required=existing.required,
        unique=True,
    )


def _semantic_dtype(column: str, semantic_profile: SemanticProfile | None) -> Any:  # noqa: ANN401
    if not semantic_profile:
        return None
    semantic = semantic_profile.columns.get(column)
    if not semantic:
        return None
    return PANDERA_DTYPE_BY_EXPECTED_TYPE.get(semantic.expected_type.lower())


def _semantic_nullable(column: str, semantic_profile: SemanticProfile | None) -> bool:
    if not semantic_profile:
        return True
    semantic = semantic_profile.columns.get(column)
    return True if semantic is None else semantic.allow_missing


def _semantic_checks(
    column: str,
    semantic_profile: SemanticProfile | None,
) -> list[pa.Check]:
    if not semantic_profile:
        return []
    semantic = semantic_profile.columns.get(column)
    if not semantic:
        return []

    checks: list[pa.Check] = []
    if semantic.potential_dmv:
        checks.append(pa.Check.notin(semantic.potential_dmv, name="no_disguised_missing_values"))
    if semantic.expected_str_pattern:
        checks.append(
            pa.Check.str_matches(semantic.expected_str_pattern, name="expected_str_pattern")
        )
    return checks


def _column_checks(column: pa.Column) -> list[pa.Check]:
    checks = column.checks
    if checks is None:
        return []
    if isinstance(checks, list):
        return checks.copy()
    return [checks]


def _safe_float(value: str, default: float) -> float:
    try:
        return float(value)
    except ValueError:
        return default
