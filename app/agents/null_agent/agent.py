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
from app.graphs.states.profiles import SemanticProfile

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
# Exceptions
# ---------------------------------------------------------------------------

class NullHandlingError(Exception):
    """Raised when null handling violates constraints or requires HITL."""
    def __init__(self, message: str, failed_rules: list[str], notes: list[str]) -> None:
        super().__init__(message)
        self.failed_rules = failed_rules
        self.notes = notes


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
        try:
            cleaned_df, dropped_per_column, filled_per_column, dropped_columns, skipped_columns, notes = (
                self._apply_null_strategies(df, agent_input.planner_task, state.get("semantic_profile"))
            )
        except NullHandlingError as exc:
            return self._failure_update(
                state,
                str(exc),
                failed_rules=exc.failed_rules,
                notes=exc.notes,
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
        semantic_profile: SemanticProfile | None = None,
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
        - ``drop_column`` : remove the entire column from the dataframe (NOT allowed per constraints).
        - ``drop_row``    : drop rows that have a null in *col*.
        - ``fill_mean``   : impute with column mean (numeric or temporal only).
        - ``fill_median`` : impute with column median (numeric or temporal only).
        - ``fill_mode``   : impute with most-frequent value (any dtype).
        - ``fill_value``  : fill nulls with ``cfg["fill_value"]`` (default ``"Unknown"``).
        - ``fill_llm``    : LLM-assisted imputation (bypassed per constraints).
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

        def get_allow_missing(col: str) -> bool:
            if semantic_profile and col in semantic_profile.columns:
                return semantic_profile.columns[col].allow_missing
            if task and task.inputs and task.inputs.column_context and col in task.inputs.column_context:
                ctx = task.inputs.column_context[col]
                semantic_dict = {}
                if hasattr(ctx, "semantic"):
                    semantic_dict = ctx.semantic
                elif isinstance(ctx, dict):
                    semantic_dict = ctx.get("semantic") or {}
                if isinstance(semantic_dict, dict):
                    return semantic_dict.get("allow_missing", True)
                elif hasattr(semantic_dict, "allow_missing"):
                    return semantic_dict.allow_missing
            return True

        def get_semantic_data_type(col: str) -> str:
            if semantic_profile and col in semantic_profile.columns:
                val = semantic_profile.columns[col].semantic_data_type
                if val:
                    return str(val).strip()
            # Fallback based on expected_type in semantic_profile or task context
            expected_type = None
            if semantic_profile and col in semantic_profile.columns:
                expected_type = semantic_profile.columns[col].expected_type
            elif task and task.inputs and task.inputs.column_context and col in task.inputs.column_context:
                ctx = task.inputs.column_context[col]
                semantic_dict = {}
                if hasattr(ctx, "semantic"):
                    semantic_dict = ctx.semantic
                elif isinstance(ctx, dict):
                    semantic_dict = ctx.get("semantic") or {}
                if isinstance(semantic_dict, dict):
                    expected_type = semantic_dict.get("expected_type")
                elif hasattr(semantic_dict, "expected_type"):
                    expected_type = semantic_dict.expected_type
            
            if expected_type:
                expected_type = str(expected_type).lower().strip()
                if expected_type == "bool":
                    return "Boolean"
                if expected_type in ("date", "datetime"):
                    return "Temporal"
                if expected_type in ("int", "integer"):
                    return "Discrete"
                if expected_type in ("float", "double", "number"):
                    return "Continuous"
            
            # Fallback based on actual pandas dtype
            dtype = str(cleaned_df[col].dtype).lower()
            if "bool" in dtype:
                return "Boolean"
            if "datetime" in dtype or "time" in dtype:
                return "Temporal"
            if "int" in dtype:
                return "Discrete"
            if "float" in dtype or "double" in dtype:
                return "Continuous"
            
            return "Nominal"

        for col, cfg in per_column.items():
            if not isinstance(cfg, dict):
                skipped_columns.append(col)
                continue

            if col not in cleaned_df.columns:
                notes.append(f"Column '{col}' not found in dataframe; skipped.")
                logger.warning("NullAgent: column '%s' not in dataframe, skipping.", col)
                continue

            strategy = cfg.get("strategy", "leave_as_is")
            allow_missing = get_allow_missing(col)
            semantic_type = get_semantic_data_type(col)

            # System constraint: drop_column is never allowed
            if strategy == "drop_column":
                skipped_columns.append(col)
                notes.append(
                    f"Column '{col}': strategy='drop_column' is prohibited by system constraints; "
                    "reverted to leave_as_is."
                )
                logger.warning("NullAgent: drop_column prohibited, skipping '%s'.", col)
                continue

            # System constraint: bypass/ignore fill_llm
            if strategy == "fill_llm":
                skipped_columns.append(col)
                notes.append(
                    f"Column '{col}': strategy='fill_llm' is ignored/bypassed; "
                    "reverted to leave_as_is."
                )
                logger.info("NullAgent: fill_llm bypassed for column '%s'.", col)
                continue

            # Calculate actual null statistics for this column
            null_mask = cleaned_df[col].isna()
            count = int(null_mask.sum())
            total = len(cleaned_df)
            null_ratio = count / total if total > 0 else 0.0

            # If no nulls found at all, skip processing
            if count == 0:
                if strategy == "drop_row":
                    dropped_per_column[col] = 0
                elif strategy in ("fill_value", "fill_mean", "fill_median", "fill_mode"):
                    filled_per_column[col] = 0
                else:
                    skipped_columns.append(col)
                notes.append(f"Column '{col}': no nulls found; nothing modified.")
                continue

            # Case: null_ratio = 100%
            if null_ratio == 1.0:
                fill_val = cfg.get("fill_value")
                if fill_val is not None:
                    # fill_constant
                    cleaned_df[col] = cleaned_df[col].fillna(fill_val)
                    filled_per_column[col] = count
                    notes.append(
                        f"Column '{col}' has 100% nulls; filled with user-defined default '{fill_val}'."
                    )
                    logger.info("NullAgent: filled 100%% null column '%s' with default '%s'.", col, fill_val)
                else:
                    if allow_missing:
                        # keep_null
                        skipped_columns.append(col)
                        notes.append(
                            f"Column '{col}' has 100% nulls and allow_missing=True; "
                            "nulls retained (keep_null)."
                        )
                        logger.info("NullAgent: keeping 100%% null column '%s' as null.", col)
                    else:
                        # HITL - raise NullHandlingError
                        message = (
                            f"Column '{col}' has 100% nulls and allow_missing=False, "
                            "but no default value (fill_value) was defined. Human-in-the-loop (HITL) required."
                        )
                        notes.append(message)
                        raise NullHandlingError(message, ["null_ratio_100_percent_no_default"], notes)
                continue

            # Coerce strategy based on semantic_type rules
            coerced_strategy = strategy

            if semantic_type == "Identifier":
                # Identifier: drop_row or keep_null (never fill)
                if strategy not in ("drop_row", "leave_as_is", "keep_null", "skip"):
                    if allow_missing:
                        coerced_strategy = "leave_as_is"
                        notes.append(
                            f"Column '{col}' (Identifier): strategy '{strategy}' coerced to 'leave_as_is' "
                            "(Identifier columns must never be filled)."
                        )
                    else:
                        coerced_strategy = "drop_row"
                        notes.append(
                            f"Column '{col}' (Identifier): strategy '{strategy}' coerced to 'drop_row' "
                            "(Identifier columns must never be filled)."
                        )
            
            elif semantic_type == "Structured text":
                # Structured text: drop_row (allow_missing=False) or keep_null (allow_missing=True)
                target_strat = "leave_as_is" if allow_missing else "drop_row"
                if strategy != target_strat and (strategy not in ("leave_as_is", "keep_null", "skip") or target_strat != "leave_as_is"):
                    coerced_strategy = target_strat
                    notes.append(
                        f"Column '{col}' (Structured text): strategy '{strategy}' coerced to '{coerced_strategy}' "
                        f"based on allow_missing={allow_missing}."
                    )
            
            elif semantic_type in ("Free text", "Geospatial", "Free text + Geospatial"):
                # Free text + Geospatial: keep_null (or fill_value/fill_constant if defined)
                if strategy == "fill_value":
                    pass # keep fill_value
                else:
                    coerced_strategy = "leave_as_is"
                    if strategy not in ("leave_as_is", "keep_null", "skip"):
                        notes.append(
                            f"Column '{col}' ({semantic_type}): strategy '{strategy}' coerced to 'leave_as_is' "
                            "unless user-defined fill_value is provided."
                        )

            elif semantic_type == "Ordinal":
                # Ordinal: fill_mode only. No mean/median.
                if strategy in ("fill_mean", "fill_median"):
                    coerced_strategy = "fill_mode"
                    notes.append(
                        f"Column '{col}' (Ordinal): strategy '{strategy}' coerced to 'fill_mode' "
                        "(mean/median calculations require encoding and are not allowed)."
                    )
            
            elif semantic_type == "Boolean":
                # Boolean: fill_mode or fill_constant.
                if strategy in ("fill_mean", "fill_median"):
                    coerced_strategy = "fill_mode"
                    notes.append(
                        f"Column '{col}' (Boolean): strategy '{strategy}' coerced to 'fill_mode' "
                        "(mean/median calculations are not applicable for Booleans)."
                    )

            # Process the coerced strategy
            if coerced_strategy == "drop_row":
                cleaned_df = cleaned_df[~null_mask].reset_index(drop=True)
                dropped_per_column[col] = count
                notes.append(f"Dropped {count} row(s) with null in column '{col}'.")
                logger.info("NullAgent: dropped %d row(s) for column '%s'.", count, col)

            elif coerced_strategy == "fill_value":
                fill_val = cfg.get("fill_value", "Unknown")
                cleaned_df[col] = cleaned_df[col].fillna(fill_val)
                filled_per_column[col] = count
                notes.append(
                    f"Filled {count} null(s) in column '{col}' with constant '{fill_val}'."
                )
                logger.info(
                    "NullAgent: filled %d null(s) in column '%s' with constant '%s'.",
                    count, col, fill_val,
                )

            elif coerced_strategy == "fill_mode":
                mode_series = cleaned_df[col].mode()
                if mode_series.empty:
                    skipped_columns.append(col)
                    notes.append(f"Column '{col}': mode calculation failed; left as-is.")
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

            elif coerced_strategy == "fill_mean":
                if semantic_type == "Temporal":
                    try:
                        # Convert to datetime and calculate mean timestamp
                        temp_series = pd.to_datetime(cleaned_df[col], errors="coerce")
                        numeric_series = temp_series.astype("int64").mask(temp_series.isna())
                        mean_ts = numeric_series.mean()
                        fill_val = pd.to_datetime(mean_ts)
                        
                        is_dt = pd.api.types.is_datetime64_any_dtype(cleaned_df[col])
                        if not is_dt:
                            fill_val = str(fill_val)
                            
                        cleaned_df[col] = cleaned_df[col].fillna(fill_val)
                        filled_per_column[col] = count
                        notes.append(
                            f"Filled {count} null(s) in Temporal column '{col}' with mean datetime='{fill_val}'."
                        )
                        logger.info(
                            "NullAgent: filled %d null(s) in temporal column '%s' with mean='%s'.",
                            count, col, fill_val,
                        )
                    except Exception as exc:
                        skipped_columns.append(col)
                        notes.append(f"Column '{col}' (Temporal): fill_mean failed with error '{exc}'; left as-is.")
                        logger.warning("NullAgent: fill_mean failed for temporal column '%s': %s", col, exc)
                else:
                    try:
                        mean_val = cleaned_df[col].mean()
                        # Discrete needs rounding
                        if semantic_type == "Discrete":
                            mean_val = round(mean_val)
                            notes.append(
                                f"Filled {count} null(s) in Discrete column '{col}' with mean={mean_val} (rounded to integer)."
                            )
                        else:
                            notes.append(
                                f"Filled {count} null(s) in column '{col}' with mean={mean_val:.4g}."
                            )
                        cleaned_df[col] = cleaned_df[col].fillna(mean_val)
                        filled_per_column[col] = count
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

            elif coerced_strategy == "fill_median":
                if semantic_type == "Temporal":
                    try:
                        # Convert to datetime and calculate median timestamp
                        temp_series = pd.to_datetime(cleaned_df[col], errors="coerce")
                        numeric_series = temp_series.astype("int64").mask(temp_series.isna())
                        median_ts = numeric_series.median()
                        fill_val = pd.to_datetime(median_ts)
                        
                        is_dt = pd.api.types.is_datetime64_any_dtype(cleaned_df[col])
                        if not is_dt:
                            fill_val = str(fill_val)
                            
                        cleaned_df[col] = cleaned_df[col].fillna(fill_val)
                        filled_per_column[col] = count
                        notes.append(
                            f"Filled {count} null(s) in Temporal column '{col}' with median datetime='{fill_val}'."
                        )
                        logger.info(
                            "NullAgent: filled %d null(s) in temporal column '%s' with median='%s'.",
                            count, col, fill_val,
                        )
                    except Exception as exc:
                        skipped_columns.append(col)
                        notes.append(f"Column '{col}' (Temporal): fill_median failed with error '{exc}'; left as-is.")
                        logger.warning("NullAgent: fill_median failed for temporal column '%s': %s", col, exc)
                else:
                    try:
                        median_val = cleaned_df[col].median()
                        # Discrete needs rounding
                        if semantic_type == "Discrete":
                            median_val = round(median_val)
                            notes.append(
                                f"Filled {count} null(s) in Discrete column '{col}' with median={median_val} (rounded to integer)."
                            )
                        else:
                            notes.append(
                                f"Filled {count} null(s) in column '{col}' with median={median_val:.4g}."
                            )
                        cleaned_df[col] = cleaned_df[col].fillna(median_val)
                        filled_per_column[col] = count
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

            elif coerced_strategy in ("leave_as_is", "skip", "keep_null"):
                skipped_columns.append(col)
                notes.append(f"Column '{col}': strategy='{coerced_strategy}'; nulls retained intentionally.")
                logger.info("NullAgent: column '%s' intentionally left with nulls.", col)

            else:
                skipped_columns.append(col)
                notes.append(f"NullAgent: strategy '{coerced_strategy}' not handled; leaving as-is.")

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
