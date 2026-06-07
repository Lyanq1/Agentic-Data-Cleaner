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
            if col in dataframe.columns:
                threshold = float(threshold_val if threshold_val is not None else 0.0)
                actual_null_rate = dataframe[col].isna().mean()
                if actual_null_rate > threshold:
                    errors.append(
                        PandasValidationError(
                            rule,
                            f"Column '{col}' null rate {actual_null_rate} exceeds threshold {threshold}.",
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
                pattern = semantic.expected_str_pattern
                non_nulls = dataframe[column_name].dropna().astype(str)
                if not non_nulls.empty:
                    match_mask = non_nulls.str.match(pattern)
                    if not match_mask.all():
                        errors.append(
                            PandasValidationError(
                                "expected_str_pattern",
                                f"Column '{column_name}' does not match expected pattern {pattern}.",
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
