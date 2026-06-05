"""Runtime entrypoints for validating the active planner task with Pandera."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pandas as pd
import pandera.pandas as pa

from app.graphs.states.global_state import ExecutionPlan, GlobalState, TaskDetail
from app.services.lineage_service import LineageService
from app.services.lineage_utils import resolve_lineage_session_id
from app.validators.models import ValidationOutcome
from app.validators.schema_builder import build_pandera_schema


def validate_current_task(state: GlobalState) -> ValidationOutcome:
    """Validate the active worker task against the latest dataframe version."""
    task = _resolve_active_task(state)
    if task is None:
        return ValidationOutcome(
            task=None,
            passed=False,
            failed_rules=["validator.execution_plan_missing"],
            message="No active work_order could be resolved from execution_plan.",
        )

    if task.skip:
        return ValidationOutcome(task=task, passed=True, skipped=True)

    dataframe = _load_latest_dataframe(state, task)
    if dataframe is None:
        return ValidationOutcome(
            task=task,
            passed=False,
            failed_rules=["validator.dataframe_missing"],
            message=(
                "No dataframe found from latest lineage version or fallback dataset path. "
                "Expected a lineage session id or a readable dataset path."
            ),
        )

    try:
        schema = build_pandera_schema(task, state.get("semantic_profile"))
        schema.validate(dataframe, lazy=True)
    except pa.errors.SchemaErrors as exc:
        return ValidationOutcome(
            task=task,
            passed=False,
            failed_rules=_failed_rules_from_schema_errors(exc, task),
            message=exc.message,
            failure_cases=_failure_cases(exc),
        )
    except pa.errors.SchemaError as exc:
        return ValidationOutcome(
            task=task,
            passed=False,
            failed_rules=_failed_rules_from_schema_error(exc, task),
            message=str(exc),
        )
    except Exception as exc:
        return ValidationOutcome(
            task=task,
            passed=False,
            failed_rules=["validator.runtime_error"],
            message=str(exc),
        )

    return ValidationOutcome(task=task, passed=True)


def _resolve_active_task(state: GlobalState) -> TaskDetail | None:
    plan_value = state.get("execution_plan")
    if plan_value is None:
        return None

    plan = plan_value
    if isinstance(plan_value, dict):
        plan = ExecutionPlan.model_validate(plan_value)

    current_idx = state.get("current_task_idx") or 0
    active_task_names = state.get("task_list") or []
    active_task_name = (
        active_task_names[current_idx] if current_idx < len(active_task_names) else None
    )

    if active_task_name:
        for wrapper in plan.task_list:
            if wrapper.work_order.task_id == active_task_name:
                return wrapper.work_order

    if current_idx < len(plan.task_list):
        return plan.task_list[current_idx].work_order

    return None


def _load_latest_dataframe(state: GlobalState, task: TaskDetail) -> pd.DataFrame | None:
    """Prefer the latest persisted lineage version, then fall back to file paths."""
    session_id = resolve_lineage_session_id(state)
    if session_id:
        try:
            dataframe = LineageService.get_latest_version(session_id)
            if not dataframe.empty:
                return dataframe
        except Exception:
            # Keep file-based validation usable for local/dev runs when lineage is unavailable.
            pass

    dataset_path = _resolve_dataset_path(state, task)
    if dataset_path:
        return _load_dataframe(dataset_path)

    return None


def _resolve_dataset_path(state: GlobalState, task: TaskDetail) -> str | None:
    candidate_keys: list[str] = []
    if task.outputs:
        candidate_keys.append(task.outputs.write_path_key)
    if task.inputs:
        candidate_keys.append(task.inputs.read_path_key)
    candidate_keys.extend(
        [
            "physical_dataframe_path",
            "dataset_version",
            "current_dataset_version",
            "dataset_path",
        ]
    )

    for key in candidate_keys:
        value = state.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _load_dataframe(dataset_path: str) -> pd.DataFrame:
    path = Path(dataset_path)
    suffix = path.suffix.lower()

    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if suffix in {".csv", ".txt"}:
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix in {".json", ".jsonl"}:
        return pd.read_json(path, lines=suffix == ".jsonl")

    raise ValueError(f"Unsupported dataset format for validation: {path.suffix or '<none>'}")


def _failure_cases(exc: pa.errors.SchemaErrors) -> list[dict[str, Any]]:
    failure_cases = exc.failure_cases
    if failure_cases is None:
        return []
    return cast(
        "list[dict[str, Any]]",
        failure_cases.where(pd.notna(failure_cases), None).to_dict(orient="records"),
    )


def _failed_rules_from_schema_errors(
    exc: pa.errors.SchemaErrors,
    task: TaskDetail,
) -> list[str]:
    cases = _failure_cases(exc)
    checks = sorted(
        {str(case.get("check")) for case in cases if case.get("check") not in {None, ""}}
    )
    if checks:
        return checks
    return _planned_rules(task) or ["pandera.schema_errors"]


def _failed_rules_from_schema_error(
    exc: pa.errors.SchemaError,
    task: TaskDetail,
) -> list[str]:
    check = getattr(exc, "check", None)
    if check:
        return [str(check)]
    return _planned_rules(task) or ["pandera.schema_error"]


def _planned_rules(task: TaskDetail) -> list[str]:
    if task.verification and task.verification.pandera_checks:
        rules = []
        for check in task.verification.pandera_checks:
            if isinstance(check, dict):
                rules.append(check.get("type", "unknown"))
            else:
                rules.append(check.type)
        return rules
    return []
