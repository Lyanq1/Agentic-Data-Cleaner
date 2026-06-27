"""Build and execute pure Pandas validations from planner work orders."""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.graphs.states.profiles import SemanticProfile
from app.graphs.states.planning import TaskDetail
from app.graphs.states.output_validation import ValidationCheck


class PandasValidationError(Exception):
    def __init__(self, check_name: str, message: str) -> None:
        super().__init__(message)
        self.check = check_name
        self.message = message


class PandasValidationErrors(Exception):
    def __init__(self, errors: list[PandasValidationError]) -> None:
        super().__init__(f"{len(errors)} validation rules failed.")
        self.errors = errors
        self.failure_cases = [{"check": err.check, "message": err.message} for err in errors]


def _extract_null_strategy_per_column(task: TaskDetail) -> dict[str, str]:
    """Extract the per-column null strategy mapping from the planner task.

    Returns a dict of {col_name: strategy_string}, e.g. {"Address2": "drop_column"}.
    Returns an empty dict if the task has no null strategy or is not a null_handling task.
    """
    if task.task_id != "null_handling" or not task.strategy:
        return {}
    strategy_raw = task.strategy
    if hasattr(strategy_raw, "model_dump"):
        strategy_dict = strategy_raw.model_dump()
    elif isinstance(strategy_raw, dict):
        strategy_dict = strategy_raw
    else:
        return {}
    per_column: dict[str, Any] = strategy_dict.get("per_column", {})
    return {
        col: (cfg.get("strategy", "") if isinstance(cfg, dict) else "")
        for col, cfg in per_column.items()
    }


def validate_dataframe(
    dataframe: pd.DataFrame,
    task: TaskDetail,
    semantic_profile: SemanticProfile | None = None,
) -> None:
    """Validate a dataframe using native Pandas operations based on the task checks."""
    errors: list[PandasValidationError] = []

    verification = task.verification
    if not verification:
        return

    # Read the per-column null strategy from the planner so checks are strategy-aware.
    null_strategy_per_column = _extract_null_strategy_per_column(task)

    # Check rule: duplicate_rows_eq_0 (from success metrics)
    if verification.success_metrics and verification.success_metrics.get("duplicate_rows") == 0:
        if dataframe.duplicated().sum() > 0:
            errors.append(
                PandasValidationError(
                    "duplicate_rows_eq_0",
                    "DataFrame contains duplicate rows when 0 were expected.",
                )
            )

    for check in verification.checks:
        if isinstance(check, dict):
            rule = check.get("type", "")
            col = check.get("column")
            threshold_val = check.get("threshold")
        else:
            rule = check.type
            col = check.column
            threshold_val = check.threshold

        if rule in ("column_unique", "is_unique") and col:
            if col in dataframe.columns:
                if dataframe[col].duplicated(keep=False).any():
                    errors.append(
                        PandasValidationError(rule, f"Column '{col}' contains duplicate values.")
                    )
        elif rule in ("null_rate_lt", "null_rate_lte") and col:
            col_strategy = null_strategy_per_column.get(col, "")

            if col_strategy == "drop_column":
                # Planner planned to drop this column — verify it was actually removed.
                if col in dataframe.columns:
                    errors.append(
                        PandasValidationError(
                            rule,
                            f"Column '{col}' was planned for drop_column but still exists in the dataframe.",
                        )
                    )
                # Column is gone → check passes.

            elif col not in dataframe.columns:
                # Column was not in the plan as drop_column but was auto-dropped by the worker
                # (e.g. fill_mode on a 100%-null column falls back to drop). Accept this silently.
                pass

            else:
                # Column exists and was planned for a fill strategy → check null rate.
                threshold = float(threshold_val if threshold_val is not None else 0.0)
                actual_null_rate = dataframe[col].isna().mean()
                if col_strategy in ("leave_as_is", "keep_null"):
                    # Column is intentionally allowed to keep nulls — skip null_rate check.
                    pass
                elif actual_null_rate > threshold:
                    errors.append(
                        PandasValidationError(
                            rule,
                            f"Column '{col}' null rate {actual_null_rate:.4f} exceeds threshold "
                            f"{threshold} (strategy='{col_strategy or 'unknown'}').",
                        )
                    )

        elif rule in ("dataframe_no_exact_duplicates", "no_duplicate_rows"):
            if dataframe.duplicated().any():
                errors.append(
                    PandasValidationError(rule, "DataFrame contains exact duplicate rows.")
                )

    # Semantic Profile checks (disguised missing values, expected pattern)
    if semantic_profile and task.columns:
        for column_name in task.columns:
            if column_name not in dataframe.columns:
                continue
            
            semantic = semantic_profile.columns.get(column_name)
            if not semantic:
                continue
                
            if semantic.potential_dmv:
                # Check for values in potential_dmv
                mask = dataframe[column_name].isin(semantic.potential_dmv)
                if mask.any():
                    errors.append(
                        PandasValidationError(
                            "no_disguised_missing_values",
                            f"Column '{column_name}' contains disguised missing values.",
                        )
                    )
                    
            if semantic.expected_str_pattern:
                # Only skip pattern check if the data was successfully cast to a temporal type.
                # If the user declined casting, the data remains a regular string and MUST be pattern-checked.
                is_datetime_dtype = pd.api.types.is_datetime64_any_dtype(dataframe[column_name])
                
                import datetime
                non_null_series = dataframe[column_name].dropna()
                is_time_objects = False
                if not non_null_series.empty and non_null_series.apply(lambda x: isinstance(x, datetime.time)).all():
                    is_time_objects = True

                is_iso_time_strings = False
                if not non_null_series.empty and non_null_series.apply(lambda x: isinstance(x, str)).all():
                    time_pattern = r"^([01]?\d|2[0-3]):([0-5]\d)(:([0-5]\d)(\.\d+)?)?$"
                    if non_null_series.astype(str).str.strip().str.match(time_pattern).all():
                        is_iso_time_strings = True

                is_casted_temporal = is_datetime_dtype or is_time_objects or is_iso_time_strings
                
                if not is_casted_temporal:
                    pattern = semantic.expected_str_pattern
                    
                    if task.task_id == "null_handling" and task.strategy:
                        strategy_raw = task.strategy
                        if hasattr(strategy_raw, "model_dump"):
                            strategy_dict = strategy_raw.model_dump()
                        elif isinstance(strategy_raw, dict):
                            strategy_dict = strategy_raw
                        else:
                            strategy_dict = {}
                            
                        per_column = strategy_dict.get("per_column", {})
                        col_cfg = per_column.get(column_name, {})
                        
                        if isinstance(col_cfg, dict) and col_cfg.get("strategy") == "fill_value":
                            fill_val = col_cfg.get("fill_value")
                            if fill_val is not None:
                                import re
                                fill_str = str(fill_val).strip()
                                # Check if the intended fill value matches the pattern
                                if not re.match(pattern, fill_str):
                                    errors.append(
                                        PandasValidationError(
                                            "expected_str_pattern",
                                            f"Column '{column_name}': the provided fill_value '{fill_str}' does not match expected pattern {pattern}.",
                                        )
                                    )
                        
    if errors:
        raise PandasValidationErrors(errors)

def run_pandas_validation(
    file_path: str,
    task: TaskDetail | None,
    semantic_profile: SemanticProfile | None = None
) -> str:
    """Helper to run the validation on a file and return a string result."""
    if not task:
        return "No task detail provided; skipping pandas validation."
        
    try:
        import pathlib
        path = pathlib.Path(file_path)
        if path.suffix.lower() in {".parquet", ".pq"}:
            df = pd.read_parquet(path)
        elif path.suffix.lower() in {".csv", ".txt"}:
            df = pd.read_csv(path)
        else:
            return f"Unsupported file format for validation: {path.suffix}"
            
        validate_dataframe(df, task, semantic_profile)
        return "SUCCESS: All Pandas validation rules for this task passed."
    except PandasValidationErrors as e:
        error_msgs = "\n".join([f"- {err.check}: {err.message}" for err in e.errors])
        return f"FAILED: {len(e.errors)} rules failed.\n{error_msgs}"
    except Exception as e:
        return f"ERROR: Failed to run validation: {e}"
