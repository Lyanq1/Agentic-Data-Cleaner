"""Utility functions for LangGraph nodes and state management."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.graphs.states.global_state import GlobalState
from app.graphs.states.planning import ExecutionPlan, TaskDetail
from app.services.dataframe_order import restore_original_column_order
from app.services.lineage_service import LineageService
from app.services.lineage_utils import resolve_lineage_session_id


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


def _load_latest_dataframe_with_source(
    state: GlobalState,
    task: TaskDetail | None,
) -> tuple[pd.DataFrame | None, str | None]:
    """Prefer the latest persisted lineage version, then fall back to file paths."""
    session_id = resolve_lineage_session_id(state)
    if session_id:
        try:
            dataframe = LineageService.get_latest_version(session_id)
            if not dataframe.empty:
                return restore_original_column_order(dataframe, state), f"lineage:{session_id}"
        except Exception:
            # Keep file-based validation usable for local/dev runs when lineage is unavailable.
            pass

    dataset_path = _resolve_dataset_path(state, task)
    if dataset_path:
        return _load_dataframe(dataset_path), dataset_path

    return None, None


def _load_latest_dataframe(state: GlobalState, task: TaskDetail | None) -> pd.DataFrame | None:
    """Compatibility wrapper returning only the dataframe."""
    dataframe, _ = _load_latest_dataframe_with_source(state, task)
    return dataframe


def _resolve_dataset_path(state: GlobalState, task: TaskDetail | None) -> str | None:
    candidate_keys: list[str] = []
    if task and task.outputs:
        candidate_keys.append(task.outputs.write_path_key)
    if task and task.inputs:
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
