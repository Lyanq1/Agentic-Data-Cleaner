"""Deterministic type-casting worker driven by the planner execution plan."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from numbers import Number
from pathlib import Path
from typing import Any

import pandas as pd

from app.agents.base import BaseAgent
from app.agents.registry import AgentRegistry
from app.agents.roles import AgentRole
from app.config.config import get_settings
from app.graphs.states.global_state import GlobalState
from app.graphs.states.planning import ExecutionPlan, TaskDetail
from app.graphs.states.profiles import SemanticProfile
from app.graphs.states.output_validation import ValidationResultItem
from app.graphs.states.workers import WorkerStateDetail, WorkerStates
from app.services.dataframe_order import restore_original_column_order
from app.services.lineage_service import LineageService
from app.services.lineage_utils import resolve_lineage_session_id

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TypeCastColumnResult:
    column: str
    expected_type: str
    before_dtype: str
    after_dtype: str
    nulls_before: int
    nulls_after: int
    coerced_nulls: int
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TypeCastingPlan:
    columns: dict[str, str]
    source: str


@AgentRegistry.auto_register
class TypeCastingAgent(BaseAgent):
    """Apply planner-requested semantic type conversions to the current dataframe."""

    name = AgentRole.TYPECAST_AGENT.value
    description = "Casts dataframe columns to planner-provided expected semantic types."
    tools: list = []

    def __init__(self) -> None:
        """Skip LLM initialization; this worker is deterministic."""

    async def run(self, state: GlobalState) -> dict[str, Any]:
        task = self._extract_planner_task(state.get("execution_plan"))
        if task is not None and task.skip:
            return self._skipped_update(state)

        plan = self._build_casting_plan(task, state.get("semantic_profile"))
        if not plan.columns:
            return self._failure_update(
                state,
                "TypeCastingAgent: no type_casting strategy.per_column expected_type values found.",
                failed_rules=["type_casting_plan_missing"],
            )

        try:
            df, read_source = self._read_current_dataframe(state)
        except Exception as exc:
            return self._failure_update(
                state,
                f"TypeCastingAgent: failed to read current dataframe: {exc}",
                failed_rules=["dataset_read_failed"],
            )

        missing_columns = [column for column in plan.columns if column not in df.columns]
        if missing_columns:
            return self._failure_update(
                state,
                f"TypeCastingAgent: columns not found in dataframe: {missing_columns}",
                failed_rules=["type_casting_columns_missing"],
            )

        before_row_count = len(df)
        result_df = df.copy()
        column_results: list[TypeCastColumnResult] = []
        failed_rules: list[str] = []

        for column, expected_type in plan.columns.items():
            before_series = result_df[column]
            before_nulls = int(before_series.isna().sum())
            try:
                after_series, notes = self._cast_series(before_series, expected_type)
            except Exception as exc:
                failed_rules.append(f"{column}_cast_failed")
                column_results.append(
                    TypeCastColumnResult(
                        column=column,
                        expected_type=expected_type,
                        before_dtype=str(before_series.dtype),
                        after_dtype=str(before_series.dtype),
                        nulls_before=before_nulls,
                        nulls_after=before_nulls,
                        coerced_nulls=0,
                        notes=[f"Cast failed: {exc}"],
                    )
                )
                continue

            result_df[column] = after_series
            after_nulls = int(result_df[column].isna().sum())
            coerced_nulls = max(after_nulls - before_nulls, 0)
            if coerced_nulls:
                notes.append(f"{coerced_nulls} value(s) could not be parsed and became null.")

            column_results.append(
                TypeCastColumnResult(
                    column=column,
                    expected_type=expected_type,
                    before_dtype=str(before_series.dtype),
                    after_dtype=str(result_df[column].dtype),
                    nulls_before=before_nulls,
                    nulls_after=after_nulls,
                    coerced_nulls=coerced_nulls,
                    notes=notes,
                )
            )

        if len(result_df) != before_row_count:
            failed_rules.append("row_count_changed_during_type_casting")

        if failed_rules:
            return self._failure_update(
                state,
                "TypeCastingAgent: type casting completed with validation-blocking issues.",
                failed_rules=failed_rules,
                partial_report=self._serialize_results(column_results, plan, read_source),
            )

        try:
            output_path = self._write_output_dataframe(result_df, state.get("project_id"))
            lineage_version = self._append_lineage_version(state, result_df, column_results)
        except Exception as exc:
            return self._failure_update(
                state,
                f"TypeCastingAgent: failed to persist cast dataframe: {exc}",
                failed_rules=["dataset_write_failed"],
            )

        worker_states = self._coerce_worker_states(state)
        worker_states.typecast_agent = WorkerStateDetail(status="done", retries=0, error_log=[])
        worker_states.last_completed_agent = self.name

        report = {
            **self._serialize_results(column_results, plan, read_source),
            "output_path": output_path,
            "lineage_version": lineage_version,
            "before_row_count": before_row_count,
            "after_row_count": len(result_df),
        }
        worker_outputs = dict(state.get("worker_outputs") or {})
        worker_outputs[self.name] = report

        logger.info(
            "TypeCastingAgent: completed | output_path=%s | columns=%s",
            output_path,
            list(plan.columns),
        )

        return {
            "physical_dataframe_path": output_path,
            "dataset_version": (
                str(lineage_version) if lineage_version is not None else state.get("dataset_version")
            ),
            "current_dataset_version": (
                str(lineage_version) if lineage_version is not None else "type_casting_v1"
            ),
            "worker_states": worker_states,
            "worker_outputs": worker_outputs,
            "validation_results": ValidationResultItem(
                agent=self.name,
                task_id="type_casting",
                passed=True,
                failed_rules=[],
                timestamp=self._timestamp(),
            ),
            "current_step": "type_casting",
            "completed_steps": "type_casting",
        }

    @staticmethod
    def _extract_planner_task(execution_plan: Any) -> TaskDetail | None:
        if not execution_plan:
            return None
        plan = ExecutionPlan.model_validate(execution_plan)
        for wrapper in plan.task_list:
            task = wrapper.work_order
            if task.task_id == "type_casting" or task.agent == AgentRole.TYPECAST_AGENT:
                return task
        return None

    def _build_casting_plan(
        self,
        task: TaskDetail | None,
        semantic_profile: SemanticProfile | None,
    ) -> TypeCastingPlan:
        columns: dict[str, str] = {}
        source = "execution_plan.strategy.per_column"

        if task:
            strategy = self._strategy_dict(task)
            per_column = strategy.get("per_column")
            if isinstance(per_column, dict):
                for column, config in per_column.items():
                    if not isinstance(config, dict):
                        continue
                    expected_type = self._normalize_expected_type(config.get("expected_type"))
                    if expected_type:
                        columns[str(column)] = expected_type

            if not columns and task.columns and semantic_profile:
                source = "execution_plan.columns + semantic_profile.expected_type"
                for column in task.columns:
                    expected_type = self._semantic_expected_type(column, semantic_profile)
                    if expected_type:
                        columns[column] = expected_type

        return TypeCastingPlan(columns=columns, source=source)

    @staticmethod
    def _strategy_dict(task: TaskDetail) -> dict[str, Any]:
        strategy = task.strategy
        if strategy is None:
            return {}
        if hasattr(strategy, "model_dump"):
            return strategy.model_dump()
        if hasattr(strategy, "dict"):
            return strategy.dict()
        return strategy if isinstance(strategy, dict) else {}

    @staticmethod
    def _semantic_expected_type(column: str, semantic_profile: SemanticProfile) -> str | None:
        semantic = semantic_profile.columns.get(column)
        if semantic is None:
            return None
        return TypeCastingAgent._normalize_expected_type(semantic.expected_type)

    @staticmethod
    def _normalize_expected_type(value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        aliases = {
            "integer": "int",
            "long": "int",
            "double": "float",
            "decimal": "float",
            "number": "float",
            "string": "str",
            "text": "str",
            "boolean": "bool",
            "timestamp": "datetime",
        }
        normalized = aliases.get(normalized, normalized)
        return normalized if normalized in {"int", "float", "str", "bool", "date", "datetime"} else None

    def _read_current_dataframe(self, state: GlobalState) -> tuple[pd.DataFrame, str]:
        source_path = state.get("physical_dataframe_path") or state.get("dataset_path")
        if source_path:
            return self._read_dataframe(str(source_path)), str(source_path)

        session_id = resolve_lineage_session_id(state)
        if session_id:
            lineage_df = LineageService.get_latest_version(session_id)
            if not lineage_df.empty:
                return restore_original_column_order(lineage_df, state), f"lineage:{session_id}"

        raise ValueError("missing physical_dataframe_path, dataset_path, and lineage dataframe")

    @staticmethod
    def _read_dataframe(dataset_path: str) -> pd.DataFrame:
        path = Path(dataset_path)
        if path.suffix.lower() in {".parquet", ".pq"}:
            return pd.read_parquet(path)
        return pd.read_csv(path)

    def _skipped_update(self, state: GlobalState) -> dict[str, Any]:
        worker_states = self._coerce_worker_states(state)
        worker_states.typecast_agent = WorkerStateDetail(status="done", retries=0, error_log=[])
        worker_states.last_completed_agent = self.name
        logger.info("TypeCastingAgent: skipped per planner work order.")
        return {
            "worker_states": worker_states,
            "validation_results": ValidationResultItem(
                agent=self.name,
                task_id="type_casting",
                passed=True,
                failed_rules=[],
                timestamp=self._timestamp(),
            ),
            "current_step": "type_casting",
            "completed_steps": "type_casting",
        }

    @staticmethod
    def _cast_series(series: pd.Series, expected_type: str) -> tuple[pd.Series, list[str]]:
        notes: list[str] = []
        non_null = series.notna()

        if expected_type == "str":
            result = series.astype("string")
            notes.append("Casted with pandas StringDtype.")
            return result, notes

        if expected_type == "float":
            result = pd.to_numeric(
                TypeCastingAgent._normalize_numeric_values(series), errors="coerce"
            ).astype("Float64")
            notes.append("Casted with pandas nullable Float64.")
            return result, notes

        if expected_type == "int":
            numeric = pd.to_numeric(
                TypeCastingAgent._normalize_numeric_values(series), errors="coerce"
            )
            fractional = numeric[non_null & numeric.notna()] % 1 != 0
            if bool(fractional.any()):
                notes.append("Non-integer numeric values were rounded to nearest integer.")
                numeric = numeric.round()
            result = numeric.astype("Int64")
            notes.append("Casted with pandas nullable Int64.")
            return result, notes

        if expected_type == "bool":
            result = series.map(TypeCastingAgent._parse_bool).astype("boolean")
            notes.append("Casted with pandas nullable BooleanDtype.")
            return result, notes

        if expected_type in ("datetime", "date"):
            import re
            from dateutil import parser
            
            as_str = series.dropna().astype(str).str.strip()
            date_pat = re.compile(
                r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b|\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b|\b\d{2}[-/]\d{1,2}[-/]\d{1,2}\b|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
                re.IGNORECASE
            )
            time_pat = re.compile(
                r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:am|pm)?\b|\b\d{1,2}\s*(?:am|pm)\b",
                re.IGNORECASE
            )
            
            has_date = as_str.apply(lambda x: bool(date_pat.search(x)))
            has_time = as_str.apply(lambda x: bool(time_pat.search(x)))
            
            if has_date.any() and has_time.any():
                first_date_str = None
                for val in as_str[has_date]:
                    try:
                        parsed = parser.parse(val)
                        first_date_str = parsed.strftime("%Y-%m-%d")
                        break
                    except Exception:
                        pass
                
                if first_date_str:
                    def fill_date(x):
                        if pd.isna(x):
                            return x
                        x_str = str(x).strip()
                        if not date_pat.search(x_str) and time_pat.search(x_str):
                            return f"{first_date_str} {x_str}"
                        return x
                    
                    series = series.apply(fill_date)
                    notes.append(f"Filled missing date components using extracted date '{first_date_str}'.")

        if expected_type == "datetime":
            result = pd.to_datetime(series, errors="coerce", format="mixed")
            notes.append("Casted with pandas datetime64 using pandas parser.")
            return result, notes

        if expected_type == "date":
            result = pd.to_datetime(series, errors="coerce", format="mixed").dt.normalize()
            notes.append("Casted to normalized pandas datetime64 date values.")
            return result, notes

        raise ValueError(f"unsupported expected_type: {expected_type}")

    @staticmethod
    def _normalize_numeric_values(series: pd.Series) -> pd.Series:
        """Extract numeric tokens from dirty strings before pandas numeric casting."""
        as_text = series.astype("string").str.strip().str.replace(",", "", regex=False)
        return as_text.str.extract(r"([-+]?\d*\.?\d+)", expand=False)

    @staticmethod
    def _parse_bool(value: Any) -> bool | None:
        if pd.isna(value):
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, Number) and value in (0, 1):
            return bool(value)
        text = str(value).strip().lower()
        if text in {"true", "t", "yes", "y", "1"}:
            return True
        if text in {"false", "f", "no", "n", "0"}:
            return False
        return None

    @staticmethod
    def _write_output_dataframe(df: pd.DataFrame, project_id: str | None) -> str:
        settings = get_settings()
        file_id = project_id or uuid.uuid4().hex[:12]
        output_dir = TypeCastingAgent._normalize_storage_path(settings.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{file_id}_type_casted.parquet"
        df.to_parquet(output_path, index=False)
        return str(output_path)

    @staticmethod
    def _append_lineage_version(
        state: GlobalState,
        df: pd.DataFrame,
        column_results: list[TypeCastColumnResult],
    ) -> int | None:
        session_id = resolve_lineage_session_id(state)
        if not session_id:
            return None
        converted_columns = [result.column for result in column_results]
        return LineageService.append_new_version(
            session_id=session_id,
            df=df,
            agent_name=AgentRole.TYPECAST_AGENT.value,
            description=f"Type-casted columns: {', '.join(converted_columns)}.",
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
    def _serialize_results(
        column_results: list[TypeCastColumnResult],
        plan: TypeCastingPlan,
        read_source: str,
    ) -> dict[str, Any]:
        return {
            "plan_source": plan.source,
            "read_source": read_source,
            "columns": [
                {
                    "column": result.column,
                    "expected_type": result.expected_type,
                    "before_dtype": result.before_dtype,
                    "after_dtype": result.after_dtype,
                    "nulls_before": result.nulls_before,
                    "nulls_after": result.nulls_after,
                    "coerced_nulls": result.coerced_nulls,
                    "notes": result.notes,
                }
                for result in column_results
            ],
        }

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
        partial_report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        worker_states = self._coerce_worker_states(state)
        retries = state.get("retry_count") or 0
        worker_states.typecast_agent = WorkerStateDetail(
            status="failed",
            retries=retries,
            error_log=worker_states.typecast_agent.error_log + [error_message],
        )

        logger.error(error_message)
        update: dict[str, Any] = {
            "worker_states": worker_states,
            "validation_results": ValidationResultItem(
                agent=self.name,
                task_id="type_casting",
                passed=False,
                failed_rules=failed_rules,
                timestamp=self._timestamp(),
            ),
            "global_errors": [error_message],
            "current_step": "type_casting",
        }
        if partial_report is not None:
            worker_outputs = dict(state.get("worker_outputs") or {})
            worker_outputs[self.name] = partial_report
            update["worker_outputs"] = worker_outputs
        return update

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()