"""Deterministic deduplication worker for exact-match simple cases."""
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
    DeduplicationResult,
    ExecutionPlan,
    GlobalState,
    StatisticalProfile,
    TaskDetail,
    ValidationResultItem,
    WorkerStateDetail,
    WorkerStates,
)

logger = logging.getLogger(__name__)


class DeduplicationAgentInput(BaseModel):
    """Runtime input contract derived from GlobalState for the dedup worker."""

    project_id: str | None = None
    dataset_path: str
    dataset_schema: dict[str, Any] | None = None
    user_prompt: str | None = None
    statistical_profile: StatisticalProfile | None = None
    planner_task: TaskDetail | None = None
    retry_count: int = 0
    hitl_feedback: str | None = None


@AgentRegistry.auto_register
class DeduplicationAgent(BaseAgent):
    """Apply deterministic exact-match deduplication on the current dataset version."""

    name = AgentRole.DEDUP_AGENT.value
    description = (
        "Runs exact full-row and exact key-based deduplication using pandas on the "
        "current dataset path."
    )
    tools: list = []

    def __init__(self) -> None:
        """Skip LLM initialization; this simple worker is deterministic."""

    async def run(self, state: GlobalState) -> dict[str, Any]:
        source_path = self._resolve_source_path(state)
        if not source_path:
            return self._failure_update(
                state,
                "DeduplicationAgent: no dataset_path or physical_dataframe_path found in state.",
                failed_rules=["missing_dataset_path"],
            )

        dedup_input = self._build_input(state, source_path)
        logger.info(
            "DeduplicationAgent: starting | source_path=%s | project_id=%s",
            dedup_input.dataset_path,
            dedup_input.project_id,
        )

        try:
            df = self._read_dataframe(dedup_input.dataset_path)
        except Exception as exc:
            return self._failure_update(
                state,
                f"DeduplicationAgent: failed to read dataset: {exc}",
                failed_rules=["dataset_read_failed"],
            )

        before_row_count = len(df)
        deduped_df = df.drop_duplicates(keep="first")
        full_row_duplicate_count = before_row_count - len(deduped_df)

        applied_modes: list[str] = []
        notes: list[str] = []
        if full_row_duplicate_count > 0:
            applied_modes.append("exact_full_row")
            notes.append(
                f"Removed {full_row_duplicate_count} exact full-row duplicate rows using keep='first'."
            )

        key_columns, key_source = self._select_key_columns(deduped_df, dedup_input)
        key_duplicate_count = 0
        duplicate_group_count = 0
        if key_columns:
            key_duplicate_count = int(
                deduped_df.duplicated(subset=key_columns, keep="first").sum()
            )
            if key_duplicate_count > 0:
                duplicate_group_count = self._count_duplicate_groups(deduped_df, key_columns)
                deduped_df = deduped_df.drop_duplicates(subset=key_columns, keep="first")
                applied_modes.append("exact_key")
                notes.append(
                    "Removed "
                    f"{key_duplicate_count} key-based duplicate rows on {key_columns} "
                    f"(source={key_source}) using keep='first'."
                )
            else:
                notes.append(
                    f"Checked key-based duplicates on {key_columns} (source={key_source}); none were detected."
                )
        else:
            notes.append("No reliable duplicate key was selected; key-based dedup was skipped.")

        if not applied_modes:
            notes.append("No duplicate rows were detected; dataset was carried forward unchanged.")

        after_row_count = len(deduped_df)
        dropped_row_count = before_row_count - after_row_count
        failed_rules = self._validate_output(deduped_df, before_row_count, key_columns)

        try:
            output_path = self._write_output_dataframe(deduped_df, dedup_input.project_id)
        except Exception as exc:
            return self._failure_update(
                state,
                f"DeduplicationAgent: failed to write deduplicated dataset: {exc}",
                failed_rules=["dataset_write_failed"],
            )

        if failed_rules:
            return self._failure_update(
                state,
                "DeduplicationAgent: post-dedup validation failed.",
                failed_rules=failed_rules,
            )

        result = DeduplicationResult(
            applied_modes=applied_modes,
            key_columns=key_columns,
            keep_strategy="first",
            source_path=dedup_input.dataset_path,
            output_path=output_path,
            before_row_count=before_row_count,
            after_row_count=after_row_count,
            dropped_row_count=dropped_row_count,
            full_row_duplicate_count=full_row_duplicate_count,
            key_duplicate_count=key_duplicate_count,
            duplicate_group_count=duplicate_group_count,
            notes=notes,
        )

        worker_states = self._coerce_worker_states(state)
        worker_states.dedup_agent = WorkerStateDetail(status="done", retries=0, error_log=[])
        worker_states.last_completed_agent = self.name

        logger.info(
            "DeduplicationAgent: completed | output_path=%s | before_rows=%s | after_rows=%s | modes=%s",
            output_path,
            before_row_count,
            after_row_count,
            applied_modes,
        )

        return {
            "deduplication_result": result,
            "physical_dataframe_path": output_path,
            "current_dataset_version": "deduplication_v1",
            "worker_states": worker_states,
            "validation_results": ValidationResultItem(
                agent=self.name,
                task_id="deduplication",
                passed=True,
                failed_rules=[],
                timestamp=self._timestamp(),
            ),
            "current_step": "deduplication",
            "completed_steps": "deduplication",
        }

    @staticmethod
    def _resolve_source_path(state: GlobalState) -> str | None:
        return state.get("physical_dataframe_path") or state.get("dataset_path")

    def _build_input(self, state: GlobalState, dataset_path: str) -> DeduplicationAgentInput:
        return DeduplicationAgentInput(
            project_id=state.get("project_id"),
            dataset_path=dataset_path,
            dataset_schema=state.get("dataset_schema"),
            user_prompt=state.get("user_prompt"),
            statistical_profile=state.get("statistical_profile"),
            planner_task=self._extract_planner_task(state.get("execution_plan")),
            retry_count=state.get("retry_count") or 0,
            hitl_feedback=state.get("hitl_feedback"),
        )

    @staticmethod
    def _extract_planner_task(execution_plan: Any) -> TaskDetail | None:
        if not execution_plan:
            return None
        plan = ExecutionPlan.model_validate(execution_plan)
        for wrapper in plan.task_list:
            task = wrapper.work_order
            if task.task_id == "deduplication" or task.agent == AgentRole.DEDUP_AGENT:
                return task
        return None

    @staticmethod
    def _read_dataframe(dataset_path: str) -> pd.DataFrame:
        path = Path(dataset_path)
        if path.suffix.lower() == ".parquet":
            return pd.read_parquet(path)
        return pd.read_csv(path)

    @staticmethod
    def _count_duplicate_groups(df: pd.DataFrame, key_columns: list[str]) -> int:
        if not key_columns:
            return 0
        group_sizes = df.groupby(key_columns, dropna=False).size()
        return int(group_sizes[group_sizes > 1].shape[0])

    def _select_key_columns(
        self,
        df: pd.DataFrame,
        dedup_input: DeduplicationAgentInput,
    ) -> tuple[list[str], str | None]:
        planner_task = dedup_input.planner_task

        if planner_task:
            val = planner_task.strategy
            if val is None:
                strategy = {}
            elif hasattr(val, "model_dump"):
                strategy = val.model_dump()
            elif hasattr(val, "dict"):
                strategy = val.dict()
            else:
                strategy = val if isinstance(val, dict) else {}

            primary_keys = strategy.get("primary_keys") or []
            if primary_keys and all(col in df.columns for col in primary_keys):
                return list(primary_keys), "execution_plan.strategy.primary_keys"
            if planner_task.columns and all(col in df.columns for col in planner_task.columns):
                return list(planner_task.columns), "execution_plan.columns"

        # Fall back to coarse EDA hints only when they actually produce duplicates.
        candidate_sets: list[tuple[list[str], str]] = []
        statistical_profile = dedup_input.statistical_profile
        if statistical_profile:
            for column in statistical_profile.near_unique_columns:
                candidate_sets.append(([column], "statistical_profile.near_unique_columns"))
            for column in statistical_profile.pk_candidates:
                candidate_sets.append(([column], "statistical_profile.pk_candidates"))

        return self._select_first_matching_candidate(df, candidate_sets)

    def _select_first_matching_candidate(
        self,
        df: pd.DataFrame,
        candidate_sets: list[tuple[list[str], str]],
    ) -> tuple[list[str], str | None]:
        for columns, source in candidate_sets:
            if not columns:
                continue
            if any(col not in df.columns for col in columns):
                continue
            if df.duplicated(subset=columns, keep=False).any():
                return columns, source
        return [], None

    def _validate_output(
        self,
        deduped_df: pd.DataFrame,
        before_row_count: int,
        key_columns: list[str],
    ) -> list[str]:
        failed_rules: list[str] = []
        if len(deduped_df) > before_row_count:
            failed_rules.append("row_count_increased_after_dedup")
        if deduped_df.duplicated(keep=False).any():
            failed_rules.append("exact_full_row_duplicates_still_present")
        if key_columns and deduped_df.duplicated(subset=key_columns, keep=False).any():
            failed_rules.append("key_duplicates_still_present")
        return failed_rules

    @staticmethod
    def _write_output_dataframe(df: pd.DataFrame, project_id: str | None) -> str:
        settings = get_settings()
        file_id = project_id or uuid.uuid4().hex[:12]
        candidate_dirs = [
            DeduplicationAgent._normalize_storage_path(settings.output_dir),
            Path.cwd() / ".tmp" / "agentic-data-cleaner" / "outputs",
        ]
        attempted_paths: list[str] = []

        for output_dir in candidate_dirs:
            if str(output_dir) in attempted_paths:
                continue
            attempted_paths.append(str(output_dir))
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
                output_path = output_dir / f"{file_id}_deduplicated.parquet"
                df.to_parquet(output_path, index=False)
                return str(output_path)
            except PermissionError:
                logger.warning(
                    "DeduplicationAgent: output_dir not writable, trying fallback | output_dir=%s",
                    output_dir,
                )

        raise PermissionError(
            "No writable output directory available for deduplication output: "
            + ", ".join(attempted_paths)
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
    ) -> dict[str, Any]:
        worker_states = self._coerce_worker_states(state)
        retries = state.get("retry_count") or 0
        worker_states.dedup_agent = WorkerStateDetail(
            status="failed",
            retries=retries,
            error_log=worker_states.dedup_agent.error_log + [error_message],
        )

        logger.error(error_message)
        return {
            "worker_states": worker_states,
            "validation_results": ValidationResultItem(
                agent=self.name,
                task_id="deduplication",
                passed=False,
                failed_rules=failed_rules,
                timestamp=self._timestamp(),
            ),
            "global_errors": error_message,
            "current_step": "deduplication",
        }
