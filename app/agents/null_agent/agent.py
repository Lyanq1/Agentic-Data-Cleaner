"""Null Agent — processes missing values according to the Planner's work order.

Supported strategies (read from ``NullStrategy.per_column``):
- ``drop_row``   : drop every row that has a null in the target column.
- ``fill_value`` : fill nulls with the value in ``cfg["fill_value"]``
                   (falls back to ``"Unknown"`` when the key is absent).
- ``leave_as_is``: skip the column intentionally; nulls are kept.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel

from app.agents.base import BaseAgent
from app.agents.registry import AgentRegistry
from app.agents.roles import AgentRole
from app.config.config import get_settings
from app.graphs.states.global_state import (
    ExecutionPlan,
    GlobalState,
    ValidationResultItem,
    WorkerStates,
)
from app.graphs.states.planning import TaskDetail
from app.graphs.states.workers import WorkerStateDetail

logger = logging.getLogger(__name__)


def _agent_log(message: str, level: str = "info") -> dict[str, Any]:
    return {
        "timestamp": datetime.now(timezone.utc).timestamp(),
        "agent": "null_agent",
        "level": level,
        "message": message,
    }


def _agent_logs_from_notes(notes: list[str]) -> list[dict[str, Any]]:
    logs: list[dict[str, Any]] = []
    for note in notes:
        level = "warning" if "unrecognised strategy" in note or "not found" in note else "info"
        logs.append(_agent_log(note, level))
    return logs


# ---------------------------------------------------------------------------
# Input contract
# ---------------------------------------------------------------------------

class NullAgentInput(BaseModel):
    """Runtime input derived from GlobalState for the Null Agent."""

    project_id: str | None = None
    dataset_path: str
    planner_task: TaskDetail | None = None
    retry_count: int = 0


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

class NullAgentResult(BaseModel):
    """Summary of what the Null Agent did."""

    source_path: str
    output_path: str
    before_row_count: int
    after_row_count: int
    dropped_row_count: int
    # Mapping of column → number of rows dropped (drop_row strategy)
    dropped_per_column: dict[str, int]
    # Mapping of column → number of cells filled
    filled_per_column: dict[str, int]
    # Columns removed entirely (drop_column strategy)
    dropped_columns: list[str]
    # Columns intentionally left unchanged (leave_as_is strategy)
    skipped_columns: list[str]
    notes: list[str]


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

@AgentRegistry.auto_register
class NullAgent(BaseAgent):
    """Drop rows where non-nullable columns contain null values.

    The agent reads the ``NullStrategy.per_column`` dict produced by the
    Planner Agent.  For every column whose ``strategy`` value is
    ``"drop_row"``, any dataframe row that has a null in that column is
    removed.  All other strategy values are currently skipped (logged as a
    note).
    """

    name = AgentRole.NULL_AGENT.value
    description = (
        "Drops rows that contain null values in columns marked as "
        "non-nullable (strategy='drop_row') according to the Planner's "
        "null handling work order."
    )
    tools: list = []

    def __init__(self) -> None:
        """Skip LLM initialisation — this worker is fully deterministic."""

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(self, state: GlobalState) -> dict[str, Any]:
        source_path = self._resolve_source_path(state)
        if not source_path:
            return self._failure_update(
                state,
                "NullAgent: no dataset_path or physical_dataframe_path found in state.",
                failed_rules=["missing_dataset_path"],
            )

        agent_input = self._build_input(state, source_path)
        logger.info(
            "NullAgent: starting | source_path=%s | project_id=%s",
            agent_input.dataset_path,
            agent_input.project_id,
        )

        # ---- Load dataframe ------------------------------------------------
        try:
            df = self._read_dataframe(agent_input.dataset_path)
        except Exception as exc:
            return self._failure_update(
                state,
                f"NullAgent: failed to read dataset: {exc}",
                failed_rules=["dataset_read_failed"],
            )

        before_row_count = len(df)

        # ---- Apply all null strategies from plan ---------------------------
        cleaned_df, dropped_per_column, filled_per_column, dropped_columns, skipped_columns, notes = (
            self._apply_null_strategies(df, agent_input.planner_task)
        )

        after_row_count = len(cleaned_df)
        dropped_row_count = before_row_count - after_row_count

        # ---- Validate output -----------------------------------------------
        failed_rules = self._validate_output(cleaned_df, before_row_count, agent_input.planner_task)

        # ---- Persist to parquet --------------------------------------------
        try:
            output_path = self._write_output_dataframe(cleaned_df, agent_input.project_id)
        except Exception as exc:
            return self._failure_update(
                state,
                f"NullAgent: failed to write cleaned dataset: {exc}",
                failed_rules=["dataset_write_failed"],
            )

        if failed_rules:
            return self._failure_update(
                state,
                "NullAgent: post-processing validation failed.",
                failed_rules=failed_rules,
                notes=notes,
            )

        # ---- Build result --------------------------------------------------
        result = NullAgentResult(
            source_path=agent_input.dataset_path,
            output_path=output_path,
            before_row_count=before_row_count,
            after_row_count=after_row_count,
            dropped_row_count=dropped_row_count,
            dropped_per_column=dropped_per_column,
            filled_per_column=filled_per_column,
            dropped_columns=dropped_columns,
            skipped_columns=skipped_columns,
            notes=notes,
        )

        worker_states = self._coerce_worker_states(state)
        worker_states.null_agent = WorkerStateDetail(status="done", retries=0, error_log=[])
        worker_states.last_completed_agent = self.name

        logger.info(
            "NullAgent: completed | output_path=%s | before_rows=%d | after_rows=%d | dropped=%d",
            output_path,
            before_row_count,
            after_row_count,
            dropped_row_count,
        )

        return {
            "worker_outputs": {"null_agent": result.model_dump()},
            "physical_dataframe_path": output_path,
            "current_dataset_version": "null_handling_v1",
            "worker_states": worker_states,
            "validation_results": ValidationResultItem(
                agent=self.name,
                task_id="null_handling",
                passed=True,
                failed_rules=[],
                timestamp=self._timestamp(),
            ),
            "current_step": "null_handling",
            "completed_steps": "null_handling",
            "agent_logs": [
                *_agent_logs_from_notes(notes),
                _agent_log(
                    f"Null handling completed. before_rows={before_row_count}, after_rows={after_row_count}, dropped={dropped_row_count}."
                ),
            ],
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_source_path(state: GlobalState) -> str | None:
        return state.get("physical_dataframe_path") or state.get("dataset_path")

    def _build_input(self, state: GlobalState, dataset_path: str) -> NullAgentInput:
        return NullAgentInput(
            project_id=state.get("project_id"),
            dataset_path=dataset_path,
            planner_task=self._extract_planner_task(state.get("execution_plan")),
            retry_count=state.get("retry_count") or 0,
        )

    @staticmethod
    def _extract_planner_task(execution_plan: Any) -> TaskDetail | None:
        """Find the null_handling task inside the ExecutionPlan."""
        if not execution_plan:
            return None
        plan = ExecutionPlan.model_validate(execution_plan)
        for wrapper in plan.task_list:
            task = wrapper.work_order
            if task.task_id == "null_handling" or task.agent == AgentRole.NULL_AGENT:
                return task
        return None

    @staticmethod
    def _apply_null_strategies(
        df: pd.DataFrame,
        task: TaskDetail | None,
    ) -> tuple[
        pd.DataFrame,          # cleaned dataframe
        dict[str, int],        # dropped_per_column
        dict[str, int],        # filled_per_column
        list[str],             # dropped_columns (drop_column strategy)
        list[str],             # skipped_columns (leave_as_is)
        list[str],             # notes
    ]:
        """Apply per-column null strategies from the Planner's work order.

        Strategies handled:
        - ``drop_column`` : remove the entire column from the dataframe.
        - ``drop_row``    : drop rows that have a null in *col*.
        - ``fill_mean``   : impute with column mean (numeric only).
        - ``fill_median`` : impute with column median (numeric only).
        - ``fill_mode``   : impute with most-frequent value (any dtype).
        - ``fill_value``  : fill nulls with ``cfg["fill_value"]`` (default ``"Unknown"``).
        - ``fill_llm``    : LLM-assisted imputation (falls back to mode).
        - ``leave_as_is`` / ``keep_null``: intentionally keep nulls.
        Any unrecognised strategy is treated as ``leave_as_is``.
        """
        cleaned_df = df.copy()
        dropped_per_column: dict[str, int] = {}
        filled_per_column: dict[str, int] = {}
        dropped_columns: list[str] = []
        skipped_columns: list[str] = []
        notes: list[str] = []

        if task is None or task.strategy is None:
            notes.append("No null handling strategy provided; dataset carried forward unchanged.")
            return cleaned_df, dropped_per_column, filled_per_column, dropped_columns, skipped_columns, notes

        # Coerce strategy to dict
        strategy_raw = task.strategy
        if hasattr(strategy_raw, "model_dump"):
            strategy_dict = strategy_raw.model_dump()
        elif isinstance(strategy_raw, dict):
            strategy_dict = strategy_raw
        else:
            notes.append("Strategy format unrecognised; dataset carried forward unchanged.")
            return cleaned_df, dropped_per_column, filled_per_column, dropped_columns, skipped_columns, notes

        per_column: dict[str, Any] = strategy_dict.get("per_column", {})

        for col, cfg in per_column.items():
            if not isinstance(cfg, dict):
                skipped_columns.append(col)
                continue

            strategy = cfg.get("strategy", "leave_as_is")

            if col not in cleaned_df.columns:
                notes.append(f"Column '{col}' not found in dataframe; skipped.")
                logger.warning("NullAgent: column '%s' not in dataframe, skipping.", col)
                continue

            if strategy == "drop_column":
                cleaned_df = cleaned_df.drop(columns=[col])
                dropped_columns.append(col)
                notes.append(f"Dropped entire column '{col}' (strategy='drop_column').")
                logger.info("NullAgent: dropped column '%s'.", col)
                continue  # column gone — skip further checks

            elif strategy == "drop_row":
                null_mask = cleaned_df[col].isna()
                count = int(null_mask.sum())
                if count > 0:
                    cleaned_df = cleaned_df[~null_mask].reset_index(drop=True)
                    dropped_per_column[col] = count
                    notes.append(f"Dropped {count} row(s) with null in column '{col}'.")
                    logger.info("NullAgent: dropped %d row(s) for column '%s'.", count, col)
                else:
                    dropped_per_column[col] = 0
                    notes.append(f"Column '{col}': no null rows found; nothing dropped.")

            elif strategy == "fill_value":
                fill_val = cfg.get("fill_value", "Unknown")
                null_mask = cleaned_df[col].isna()
                count = int(null_mask.sum())
                if count > 0:
                    cleaned_df[col] = cleaned_df[col].fillna(fill_val)
                    filled_per_column[col] = count
                    notes.append(
                        f"Filled {count} null(s) in column '{col}' with constant '{fill_val}'."
                    )
                    logger.info(
                        "NullAgent: filled %d null(s) in column '%s' with constant '%s'.",
                        count, col, fill_val,
                    )
                else:
                    filled_per_column[col] = 0
                    notes.append(f"Column '{col}': no nulls found; nothing filled.")

            elif strategy == "fill_mean":
                null_mask = cleaned_df[col].isna()
                count = int(null_mask.sum())
                if count > 0:
                    try:
                        mean_val = cleaned_df[col].mean()
                        cleaned_df[col] = cleaned_df[col].fillna(mean_val)
                        filled_per_column[col] = count
                        notes.append(
                            f"Filled {count} null(s) in column '{col}' with mean={mean_val:.4g}."
                        )
                        logger.info(
                            "NullAgent: filled %d null(s) in column '%s' with mean=%s.",
                            count, col, mean_val,
                        )
                    except TypeError:
                        skipped_columns.append(col)
                        message = (
                            f"NullAgent: fill_mean not applicable for non-numeric column '{col}'; "
                            "leaving as-is."
                        )
                        notes.append(message)
                        logger.warning(message)
                else:
                    filled_per_column[col] = 0
                    notes.append(f"Column '{col}': no nulls found; nothing filled.")

            elif strategy == "fill_median":
                null_mask = cleaned_df[col].isna()
                count = int(null_mask.sum())
                if count > 0:
                    try:
                        median_val = cleaned_df[col].median()
                        cleaned_df[col] = cleaned_df[col].fillna(median_val)
                        filled_per_column[col] = count
                        notes.append(
                            f"Filled {count} null(s) in column '{col}' with median={median_val:.4g}."
                        )
                        logger.info(
                            "NullAgent: filled %d null(s) in column '%s' with median=%s.",
                            count, col, median_val,
                        )
                    except TypeError:
                        skipped_columns.append(col)
                        message = (
                            f"NullAgent: fill_median not applicable for non-numeric column '{col}'; "
                            "leaving as-is."
                        )
                        notes.append(message)
                        logger.warning(message)
                else:
                    filled_per_column[col] = 0
                    notes.append(f"Column '{col}': no nulls found; nothing filled.")

            elif strategy == "fill_mode":
                null_mask = cleaned_df[col].isna()
                count = int(null_mask.sum())
                if count > 0:
                    mode_series = cleaned_df[col].mode()
                    if mode_series.empty:
                        # All values are null — mode is undefined. Drop the column entirely
                        # because a 100%-null column has no imputable or analytical value.
                        cleaned_df = cleaned_df.drop(columns=[col])
                        dropped_columns.append(col)
                        message = (
                            f"Column '{col}': fill_mode failed (all {count} values are null, "
                            "no mode can be computed). Auto-dropped the column."
                        )
                        notes.append(message)
                        logger.warning(message)
                        continue
                    else:
                        mode_val = mode_series.iloc[0]
                        cleaned_df[col] = cleaned_df[col].fillna(mode_val)
                        filled_per_column[col] = count
                        notes.append(
                            f"Filled {count} null(s) in column '{col}' with mode='{mode_val}'."
                        )
                        logger.info(
                            "NullAgent: filled %d null(s) in column '%s' with mode='%s'.",
                            count, col, mode_val,
                        )
                else:
                    filled_per_column[col] = 0
                    notes.append(f"Column '{col}': no nulls found; nothing filled.")

            elif strategy == "fill_llm":
                # LLM-assisted imputation: NullAgent is deterministic, so fall back to mode.
                # If 100% null (mode undefined), auto-drop like fill_mode.
                null_mask = cleaned_df[col].isna()
                count = int(null_mask.sum())
                if count > 0:
                    mode_series = cleaned_df[col].mode()
                    if mode_series.empty:
                        cleaned_df = cleaned_df.drop(columns=[col])
                        dropped_columns.append(col)
                        message = (
                            f"fill_llm requested for column '{col}' but all {count} values are null "
                            "(no mode fallback possible). Auto-dropped the column."
                        )
                        notes.append(message)
                        logger.warning(message)
                        continue
                    fill_val = mode_series.iloc[0]
                    cleaned_df[col] = cleaned_df[col].fillna(fill_val)
                    filled_per_column[col] = count
                    message = (
                        f"fill_llm requested for column '{col}' but NullAgent is deterministic; "
                        f"fell back to mode-fill with '{fill_val}' for {count} null(s)."
                    )
                    notes.append(message)
                    logger.warning(message)
                else:
                    filled_per_column[col] = 0
                    notes.append(f"Column '{col}': no nulls found; nothing filled.")

            elif strategy in ("leave_as_is", "skip", "keep_null"):
                skipped_columns.append(col)
                notes.append(f"Column '{col}': strategy='leave_as_is'; nulls retained intentionally.")
                logger.info("NullAgent: column '%s' intentionally left with nulls.", col)

            else:
                # Unknown strategy → treat as leave_as_is
                skipped_columns.append(col)
                message = (
                    f"NullAgent: unrecognised strategy '{strategy}' for column '{col}'; "
                    "leaving as-is."
                )
                notes.append(message)
                logger.warning(message)

        return cleaned_df, dropped_per_column, filled_per_column, dropped_columns, skipped_columns, notes

    @staticmethod
    def _read_dataframe(dataset_path: str) -> pd.DataFrame:
        path = Path(dataset_path)
        if path.suffix.lower() in {".parquet", ".pq"}:
            return pd.read_parquet(path)
        if path.suffix.lower() in {".csv", ".txt"}:
            return pd.read_csv(path)
        if path.suffix.lower() in {".xlsx", ".xls"}:
            return pd.read_excel(path)
        if path.suffix.lower() in {".json", ".jsonl"}:
            return pd.read_json(path, lines=path.suffix.lower() == ".jsonl")
        raise ValueError(f"Unsupported dataset format: {path.suffix}")

    def _validate_output(
        self,
        df: pd.DataFrame,
        before_row_count: int,
        task: TaskDetail | None,
    ) -> list[str]:
        """Basic sanity checks after processing."""
        failed: list[str] = []

        # Row count must not increase
        if len(df) > before_row_count:
            failed.append("row_count_increased_after_null_handling")

        # must_preserve_row_count is False when drop_row is applied,
        # but if the planner explicitly set it to True and we still dropped rows,
        # that is a conflict we should surface.
        if task and task.outputs and task.outputs.must_preserve_row_count:
            if len(df) < before_row_count:
                failed.append(
                    "must_preserve_row_count_violated: rows were dropped but "
                    "task.outputs.must_preserve_row_count=True"
                )

        return failed

    @staticmethod
    def _write_output_dataframe(df: pd.DataFrame, project_id: str | None) -> str:
        settings = get_settings()
        file_id = project_id or uuid.uuid4().hex[:12]

        candidate_dirs = [
            NullAgent._normalize_storage_path(settings.output_dir),
            Path.cwd() / ".tmp" / "agentic-data-cleaner" / "outputs",
        ]
        attempted: list[str] = []

        for output_dir in candidate_dirs:
            if str(output_dir) in attempted:
                continue
            attempted.append(str(output_dir))
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
                output_path = output_dir / f"{file_id}_null_handled.parquet"
                df.to_parquet(output_path, index=False)
                return str(output_path)
            except PermissionError:
                logger.warning(
                    "NullAgent: output_dir not writable, trying fallback | output_dir=%s",
                    output_dir,
                )

        raise PermissionError(
            "No writable output directory available for null handling output: "
            + ", ".join(attempted)
        )

    @staticmethod
    def _normalize_storage_path(raw_path: str) -> Path:
        path = Path(raw_path)
        if path.is_absolute():
            return path
        path_str = str(path)
        if path_str.startswith(("\\", "/")):
            return Path(Path.cwd().anchor) / path_str.lstrip("\\/")
        return Path.cwd() / path

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _coerce_worker_states(state: GlobalState) -> WorkerStates:
        existing = state.get("worker_states")
        if hasattr(existing, "model_dump"):
            payload = existing.model_dump()
        elif isinstance(existing, dict):
            payload = existing
        else:
            payload = {}

        return WorkerStates(
            last_completed_agent=payload.get("last_completed_agent"),
            dedup_agent=WorkerStateDetail.model_validate(
                payload.get("dedup_agent") or {"status": "pending"}
            ),
            null_agent=WorkerStateDetail.model_validate(
                payload.get("null_agent") or {"status": "pending"}
            ),
            typecast_agent=WorkerStateDetail.model_validate(
                payload.get("typecast_agent") or {"status": "pending"}
            ),
        )

    def _failure_update(
        self,
        state: GlobalState,
        error_message: str,
        *,
        failed_rules: list[str],
        notes: list[str] | None = None,
    ) -> dict[str, Any]:
        worker_states = self._coerce_worker_states(state)
        retries = state.get("retry_count") or 0
        worker_states.null_agent = WorkerStateDetail(
            status="failed",
            retries=retries,
            error_log=worker_states.null_agent.error_log + [error_message],
        )

        logger.error(error_message)
        return {
            "worker_states": worker_states,
            "validation_results": ValidationResultItem(
                agent=self.name,
                task_id="null_handling",
                passed=False,
                failed_rules=failed_rules,
                timestamp=self._timestamp(),
            ),
            "global_errors": error_message,
            "current_step": "null_handling",
            "agent_logs": [
                *_agent_logs_from_notes(notes or []),
                _agent_log(error_message, "error"),
            ],
        }
