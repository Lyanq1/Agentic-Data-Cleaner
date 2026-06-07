"""Hybrid deduplication agent with LLM strategy selection and deterministic execution."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from app.agents.base import BaseAgent
from app.agents.deduplication.models import (
    DedupDecision,
    DeduplicationAgentInput,
    ValidatedDedupDecision,
)
from app.agents.deduplication.prompt import (
    DEDUP_DECISION_JSON_INSTRUCTION,
    build_dedup_messages,
)
from app.agents.registry import AgentRegistry
from app.agents.roles import AgentRole
from app.config.config import get_settings
from app.core.llm_factory import create_llm
from app.graphs.states.global_state import GlobalState
from app.graphs.states.output_validation import ValidationResultItem
from app.graphs.states.planning import ExecutionPlan, TaskDetail
from app.graphs.states.profiler_state import StatisticalProfile
from app.graphs.states.profiles import SemanticProfile
from app.graphs.states.workers import (
    DedupDecisionTrace,
    DeduplicationResult,
    WorkerStateDetail,
    WorkerStates,
)
from app.tools.data.dedup import inspect_duplicate_candidates

logger = logging.getLogger(__name__)


@AgentRegistry.auto_register
class DeduplicationAgent(BaseAgent):
    """Choose a dedup strategy with the LLM, then execute it deterministically."""

    name = AgentRole.DEDUP_AGENT.value
    description = (
        "Selects a deduplication strategy with tool-assisted LLM reasoning, then runs "
        "exact full-row and exact key-based deduplication deterministically."
    )
    tools = [inspect_duplicate_candidates]

    def __init__(self) -> None:
        super().__init__()
        self.json_llm = create_llm()
        self._tool_map = {tool.name: tool for tool in self.tools}

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
            context_hash = self._compute_context_hash(dedup_input)
            validated_decision = self._extract_debug_override_decision(dedup_input, df)
            if validated_decision is None:
                validated_decision = self._rebuild_decision_from_state(state, context_hash)

            reused_decision = validated_decision is not None
            if validated_decision is None:
                context = self._build_decision_context(dedup_input)
                raw_decision = await self._invoke_dedup_decision_llm(context)
                validated_decision = self._validate_dedup_decision(raw_decision, df, dedup_input)

            execution = self._execute_validated_decision(df, validated_decision)
            notes = list(execution["notes"])
            if reused_decision:
                notes.append("Reused the previous dedup decision because the context hash matched.")
            failed_rules = self._validate_output(
                execution["deduped_df"],
                execution["before_row_count"],
                validated_decision.key_columns if validated_decision.mode == "exact_key" else [],
            )

            output_path = self._write_output_dataframe(
                execution["deduped_df"],
                dedup_input.project_id,
            )
        except Exception as exc:
            return self._failure_update(
                state,
                f"DeduplicationAgent: failed during execution: {exc}",
                failed_rules=["dedup_execution_failed"],
            )

        if failed_rules:
            return self._failure_update(
                state,
                "DeduplicationAgent: post-dedup validation failed.",
                failed_rules=failed_rules,
            )

        result = DeduplicationResult(
            applied_modes=execution["applied_modes"],
            key_columns=validated_decision.key_columns if validated_decision.mode == "exact_key" else [],
            keep_strategy="first",
            source_path=dedup_input.dataset_path,
            output_path=output_path,
            before_row_count=execution["before_row_count"],
            after_row_count=execution["after_row_count"],
            dropped_row_count=execution["dropped_row_count"],
            full_row_duplicate_count=execution["full_row_duplicate_count"],
            key_duplicate_count=execution["key_duplicate_count"],
            duplicate_group_count=execution["duplicate_group_count"],
            notes=notes,
            decision_trace=validated_decision.to_trace(context_hash=context_hash),
        )

        worker_states = self._coerce_worker_states(state)
        worker_states.dedup_agent = WorkerStateDetail(status="done", retries=0, error_log=[])
        worker_states.last_completed_agent = self.name

        logger.info(
            "DeduplicationAgent: completed | output_path=%s | before_rows=%s | after_rows=%s | modes=%s | source=%s",
            output_path,
            execution["before_row_count"],
            execution["after_row_count"],
            execution["applied_modes"],
            validated_decision.decision_source,
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
                metrics_observed={
                    "before_row_count": execution["before_row_count"],
                    "after_row_count": execution["after_row_count"],
                    "decision_source": validated_decision.decision_source,
                },
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
            semantic_profile=state.get("semantic_profile"),
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

    def _extract_debug_override_decision(
        self,
        dedup_input: DeduplicationAgentInput,
        df: pd.DataFrame,
    ) -> ValidatedDedupDecision | None:
        planner_task = dedup_input.planner_task
        if not planner_task or planner_task.rationale != "Injected by the debug dedup endpoint.":
            return None

        key_columns = [column for column in planner_task.columns if column in df.columns]
        if not key_columns:
            return ValidatedDedupDecision(
                mode="exact_full_row",
                key_columns=[],
                ignore_columns=[],
                decision_source="planner_fallback",
                confidence=1.0,
                reasoning_summary="Debug override was invalid, so the agent fell back to exact full-row dedup.",
                validation_notes=["Debug override supplied no usable key columns."],
            )

        return ValidatedDedupDecision(
            mode="exact_key",
            key_columns=key_columns,
            ignore_columns=[],
            decision_source="planner_fallback",
            confidence=1.0,
            reasoning_summary="Used the service-layer debug override for key-based dedup testing.",
            validation_notes=["Debug override applied at the service layer."],
        )

    def _build_decision_context(self, dedup_input: DeduplicationAgentInput) -> dict[str, Any]:
        statistical_profile = self._to_dict(dedup_input.statistical_profile) or {}
        semantic_profile = self._to_dict(dedup_input.semantic_profile) or {}
        planner_task = self._planner_task_summary(dedup_input.planner_task)
        columns = []
        for column in (dedup_input.statistical_profile.columns if dedup_input.statistical_profile else []):
            semantic_detail = (dedup_input.semantic_profile.columns.get(column.column_name) if dedup_input.semantic_profile else None)
            columns.append(
                {
                    "name": column.column_name,
                    "dtype": column.dtype,
                    "null_rate": column.null_rate,
                    "unique_ratio": column.unique_ratio,
                    "detected_patterns": column.detected_patterns,
                    "sample_values": column.sample_values[:5],
                    "semantic_group": semantic_detail.logical_group if semantic_detail else None,
                    "semantic_description": semantic_detail.description if semantic_detail else None,
                }
            )

        return {
            "dataset_path": dedup_input.dataset_path,
            "user_prompt": dedup_input.user_prompt or "",
            "dataset_schema": dedup_input.dataset_schema or {},
            "table_summary": semantic_profile.get("table_summary"),
            "pk_candidates": statistical_profile.get("pk_candidates", []),
            "near_unique_columns": statistical_profile.get("near_unique_columns", []),
            "high_null_columns": statistical_profile.get("high_null_columns", []),
            "planner_task": planner_task,
            "suggested_candidate_sets": self._build_suggested_candidate_sets(dedup_input),
            "columns": columns,
        }

    async def _invoke_dedup_decision_llm(self, context: dict[str, Any]) -> DedupDecision:
        messages = build_dedup_messages(context)
        messages = await self._run_tool_loop(messages)
        messages.append(SystemMessage(content=DEDUP_DECISION_JSON_INSTRUCTION))
        content_clean = None
        try:
            json_llm = self.json_llm.bind(response_format={"type": "json_object"})
            raw_response = await json_llm.ainvoke(messages)
            content = raw_response.content if isinstance(raw_response.content, str) else json.dumps(raw_response.content)
            content_clean = self._clean_json_content(content)
            return DedupDecision.model_validate_json(content_clean)
        except Exception as exc:
            logger.warning("DeduplicationAgent: failed to parse LLM decision, using review_needed fallback. error=%s", exc)
            return DedupDecision(
                mode="review_needed",
                key_columns=[],
                ignore_columns=[],
                confidence=0.0,
                reasoning_summary="The LLM decision could not be parsed, so deterministic fallback will be used.",
            )

    async def _run_tool_loop(self, messages: list) -> list:
        working_messages = list(messages)
        for _ in range(3):
            response = await self.llm.ainvoke(working_messages)
            working_messages.append(response)
            tool_calls = getattr(response, "tool_calls", None) or []
            if not tool_calls:
                break

            for tool_call in tool_calls:
                tool = self._tool_map.get(tool_call["name"])
                if tool is None:
                    tool_result = {"error": f"Unknown tool: {tool_call['name']}"}
                else:
                    try:
                        tool_result = tool.invoke(tool_call["args"])
                    except Exception as exc:
                        tool_result = {"error": str(exc)}
                working_messages.append(
                    ToolMessage(
                        content=json.dumps(tool_result, ensure_ascii=False, default=str),
                        tool_call_id=tool_call["id"],
                    )
                )
        return working_messages

    def _validate_dedup_decision(
        self,
        decision: DedupDecision,
        df: pd.DataFrame,
        dedup_input: DeduplicationAgentInput,
    ) -> ValidatedDedupDecision:
        null_rates = self._column_null_rates(dedup_input.statistical_profile)
        requested = self._dedupe_columns(
            [column for column in decision.key_columns if column not in set(decision.ignore_columns)]
        )
        missing = [column for column in requested if column not in df.columns]
        if decision.mode == "review_needed":
            return self._fallback_decision(
                df,
                dedup_input,
                validation_notes=["LLM returned review_needed; collapsing to deterministic fallback."],
                reasoning_summary=decision.reasoning_summary or "The LLM did not find a reliable key.",
            )
        if missing:
            return self._fallback_decision(
                df,
                dedup_input,
                validation_notes=[f"LLM selected missing columns: {missing}"],
                reasoning_summary=decision.reasoning_summary or "The LLM selected invalid columns.",
            )

        filtered = list(requested)
        removed_high_null = [column for column in filtered if null_rates.get(column, 0.0) > 0.30]
        filtered = [column for column in filtered if column not in removed_high_null]
        validation_notes: list[str] = []
        if removed_high_null:
            validation_notes.append(
                f"Removed high-null key columns from the LLM decision: {removed_high_null}."
            )
        if decision.mode == "exact_key" and not filtered:
            return self._fallback_decision(
                df,
                dedup_input,
                validation_notes=validation_notes + ["No usable key columns remained after validation."],
                reasoning_summary=decision.reasoning_summary or "The LLM key set collapsed during validation.",
            )
        if decision.mode == "exact_key" and len(filtered) == 1 and self._looks_like_technical_id(filtered[0], dedup_input):
            validation_notes.append(
                f"Downgraded single-column technical identifier '{filtered[0]}' to exact full-row dedup."
            )
            return ValidatedDedupDecision(
                mode="exact_full_row",
                key_columns=[],
                ignore_columns=list(decision.ignore_columns),
                decision_source="safe_default",
                confidence=decision.confidence,
                reasoning_summary=decision.reasoning_summary or "Technical row identifiers are not used as the only dedup key.",
                validation_notes=validation_notes,
            )
        if decision.mode == "exact_key" and all(null_rates.get(column, 0.0) > 0.80 for column in filtered):
            return self._fallback_decision(
                df,
                dedup_input,
                validation_notes=validation_notes + ["All candidate key columns were null in more than 80% of rows."],
                reasoning_summary=decision.reasoning_summary or "The LLM key set was too sparse to trust.",
            )

        if decision.mode == "exact_key":
            if len(filtered) == 1 and not self._looks_like_strong_identifier(filtered[0], dedup_input):
                validation_notes.append(
                    f"Single-column key '{filtered[0]}' is not a strong identifier; proceeding with caution."
                )
            if decision.confidence is not None and decision.confidence < 0.6:
                validation_notes.append("LLM confidence was below 0.6; proceeding because the key set passed deterministic validation.")
            return ValidatedDedupDecision(
                mode="exact_key",
                key_columns=filtered,
                ignore_columns=list(decision.ignore_columns),
                decision_source="llm",
                confidence=decision.confidence,
                reasoning_summary=decision.reasoning_summary,
                validation_notes=validation_notes,
            )

        if decision.confidence is not None and decision.confidence < 0.6:
            validation_notes.append("LLM confidence was below 0.6; proceeding with exact full-row dedup.")
        return ValidatedDedupDecision(
            mode="exact_full_row",
            key_columns=[],
            ignore_columns=list(decision.ignore_columns),
            decision_source="llm",
            confidence=decision.confidence,
            reasoning_summary=decision.reasoning_summary,
            validation_notes=validation_notes,
        )

    def _fallback_decision(
        self,
        df: pd.DataFrame,
        dedup_input: DeduplicationAgentInput,
        *,
        validation_notes: list[str],
        reasoning_summary: str,
    ) -> ValidatedDedupDecision:
        planner_task = dedup_input.planner_task
        if planner_task:
            strategy = self._to_dict(planner_task.strategy) or {}
            primary_keys = self._dedupe_columns(strategy.get("primary_keys") or [])
            if primary_keys and self._candidate_has_duplicates(df, primary_keys):
                return ValidatedDedupDecision(
                    mode="exact_key",
                    key_columns=primary_keys,
                    ignore_columns=[],
                    decision_source="planner_fallback",
                    confidence=None,
                    reasoning_summary=reasoning_summary,
                    validation_notes=validation_notes + ["Used planner strategy.primary_keys as fallback."],
                )
            planner_columns = self._dedupe_columns(planner_task.columns)
            if planner_columns and self._candidate_has_duplicates(df, planner_columns):
                return ValidatedDedupDecision(
                    mode="exact_key",
                    key_columns=planner_columns,
                    ignore_columns=[],
                    decision_source="planner_fallback",
                    confidence=None,
                    reasoning_summary=reasoning_summary,
                    validation_notes=validation_notes + ["Used planner task columns as fallback."],
                )

        if dedup_input.statistical_profile:
            candidate_sets: list[list[str]] = []
            for column in dedup_input.statistical_profile.near_unique_columns:
                candidate_sets.append([column])
            for column in dedup_input.statistical_profile.pk_candidates:
                candidate_sets.append([column])

            for candidate in candidate_sets:
                if self._candidate_has_duplicates(df, candidate):
                    return ValidatedDedupDecision(
                        mode="exact_key",
                        key_columns=candidate,
                        ignore_columns=[],
                        decision_source="profile_fallback",
                        confidence=None,
                        reasoning_summary=reasoning_summary,
                        validation_notes=validation_notes + [f"Used statistical profile candidate {candidate} as fallback."],
                    )

        return ValidatedDedupDecision(
            mode="exact_full_row",
            key_columns=[],
            ignore_columns=[],
            decision_source="safe_default",
            confidence=None,
            reasoning_summary=reasoning_summary,
            validation_notes=validation_notes + ["Fell back to exact full-row dedup."],
        )

    def _execute_validated_decision(
        self,
        df: pd.DataFrame,
        validated_decision: ValidatedDedupDecision,
    ) -> dict[str, Any]:
        before_row_count = len(df)
        deduped_df = df.drop_duplicates(keep="first")
        full_row_duplicate_count = before_row_count - len(deduped_df)

        applied_modes: list[str] = []
        notes: list[str] = [
            f"Decision source: {validated_decision.decision_source}.",
            f"Decision rationale: {validated_decision.reasoning_summary}",
        ]
        if validated_decision.validation_notes:
            notes.extend(validated_decision.validation_notes)

        if full_row_duplicate_count > 0:
            applied_modes.append("exact_full_row")
            notes.append(
                f"Removed {full_row_duplicate_count} exact full-row duplicate rows using keep='first'."
            )

        key_duplicate_count = 0
        duplicate_group_count = 0
        if validated_decision.mode == "exact_key" and validated_decision.key_columns:
            key_duplicate_count = int(
                deduped_df.duplicated(subset=validated_decision.key_columns, keep="first").sum()
            )
            if key_duplicate_count > 0:
                duplicate_group_count = self._count_duplicate_groups(
                    deduped_df,
                    validated_decision.key_columns,
                )
                deduped_df = deduped_df.drop_duplicates(
                    subset=validated_decision.key_columns,
                    keep="first",
                )
                applied_modes.append("exact_key")
                notes.append(
                    "Removed "
                    f"{key_duplicate_count} key-based duplicate rows on {validated_decision.key_columns} "
                    "using keep='first'."
                )
            else:
                notes.append(
                    f"Checked key-based duplicates on {validated_decision.key_columns}; none were detected."
                )
        elif validated_decision.mode == "exact_full_row":
            notes.append("Exact full-row dedup was selected as the final strategy.")

        after_row_count = len(deduped_df)
        if not applied_modes:
            notes.append("No duplicate rows were detected; dataset was carried forward unchanged.")

        return {
            "deduped_df": deduped_df,
            "applied_modes": applied_modes,
            "before_row_count": before_row_count,
            "after_row_count": after_row_count,
            "dropped_row_count": before_row_count - after_row_count,
            "full_row_duplicate_count": full_row_duplicate_count,
            "key_duplicate_count": key_duplicate_count,
            "duplicate_group_count": duplicate_group_count,
            "notes": notes,
        }

    def _rebuild_decision_from_state(
        self,
        state: GlobalState,
        context_hash: str,
    ) -> ValidatedDedupDecision | None:
        existing_result = state.get("deduplication_result")
        if not existing_result:
            return None
        result = DeduplicationResult.model_validate(existing_result)
        trace = result.decision_trace
        if trace is None or trace.context_hash != context_hash:
            return None

        mode = "exact_key" if result.key_columns else "exact_full_row"
        return ValidatedDedupDecision(
            mode=mode,
            key_columns=list(result.key_columns),
            ignore_columns=list(trace.ignore_columns),
            decision_source=trace.decision_source,
            confidence=trace.confidence,
            reasoning_summary=trace.reasoning_summary,
            validation_notes=list(trace.validation_notes),
        )

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

    def _candidate_has_duplicates(self, df: pd.DataFrame, columns: list[str]) -> bool:
        if not columns or any(column not in df.columns for column in columns):
            return False
        return bool(df.duplicated(subset=columns, keep=False).any())

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

    def _compute_context_hash(self, dedup_input: DeduplicationAgentInput) -> str:
        statistical_profile = dedup_input.statistical_profile
        semantic_profile = dedup_input.semantic_profile
        semantic_columns = {}
        if semantic_profile:
            for name, detail in semantic_profile.columns.items():
                semantic_columns[name] = {
                    "logical_group": detail.logical_group,
                    "expected_type": detail.expected_type,
                    "expected_pattern": detail.expected_str_pattern,
                    "description": detail.description,
                }

        payload = {
            "dataset_schema": sorted((dedup_input.dataset_schema or {}).keys()),
            "null_rates": self._column_null_rates(statistical_profile),
            "pk_candidates": list(statistical_profile.pk_candidates) if statistical_profile else [],
            "near_unique_columns": list(statistical_profile.near_unique_columns) if statistical_profile else [],
            "semantic_columns": semantic_columns,
            "user_prompt": dedup_input.user_prompt or "",
            "planner_task": self._planner_task_summary(dedup_input.planner_task),
        }
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _column_null_rates(profile: StatisticalProfile | None) -> dict[str, float]:
        if not profile:
            return {}
        return {column.column_name: float(column.null_rate) for column in profile.columns}

    def _build_suggested_candidate_sets(self, dedup_input: DeduplicationAgentInput) -> list[list[str]]:
        available = set((dedup_input.dataset_schema or {}).keys())
        suggestions: list[list[str]] = []
        planner_task = dedup_input.planner_task
        if planner_task:
            strategy = self._to_dict(planner_task.strategy) or {}
            if strategy.get("primary_keys"):
                suggestions.append(list(strategy["primary_keys"]))
            if planner_task.columns:
                suggestions.append(list(planner_task.columns))
        if dedup_input.statistical_profile:
            for column in dedup_input.statistical_profile.pk_candidates:
                suggestions.append([column])
            for column in dedup_input.statistical_profile.near_unique_columns:
                suggestions.append([column])

        common_sets = [
            ["Site name", "Address"],
            ["Source", "Site name", "Address"],
            ["Site name", "Address", "Phone"],
            ["Address", "Phone"],
            ["Source", "Address", "Phone", "Program Name"],
        ]
        for candidate in common_sets:
            if all(column in available for column in candidate):
                suggestions.append(candidate)

        seen: set[tuple[str, ...]] = set()
        unique_suggestions: list[list[str]] = []
        for candidate in suggestions:
            normalized = tuple(candidate)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            unique_suggestions.append(list(candidate))
        return unique_suggestions[:8]

    def _looks_like_technical_id(self, column_name: str, dedup_input: DeduplicationAgentInput) -> bool:
        normalized = column_name.strip().lower()
        if normalized in {"id", "_id", "row_id", "record_id"} or normalized.endswith("_id"):
            return True

        profile = dedup_input.semantic_profile.columns.get(column_name) if dedup_input.semantic_profile else None
        if profile:
            description = profile.description.lower()
            if "record" in description and "identifier" in description:
                return True
            if normalized == "id" and profile.logical_group.lower() == "identity":
                return True
        return False

    def _looks_like_strong_identifier(self, column_name: str, dedup_input: DeduplicationAgentInput) -> bool:
        normalized = column_name.strip().lower()
        if any(token in normalized for token in ["email", "phone", "provider", "license", "account"]):
            return True

        statistical_profile = dedup_input.statistical_profile
        if statistical_profile:
            for column in statistical_profile.columns:
                if column.column_name == column_name and column.unique_ratio >= 0.90:
                    return True
        return False

    @staticmethod
    def _planner_task_summary(planner_task: TaskDetail | None) -> dict[str, Any] | None:
        if planner_task is None:
            return None
        strategy = DeduplicationAgent._to_dict(planner_task.strategy)
        return {
            "task_id": planner_task.task_id,
            "columns": list(planner_task.columns),
            "rationale": planner_task.rationale,
            "strategy": strategy,
        }

    @staticmethod
    def _to_dict(obj: Any) -> Any:
        if obj is None:
            return None
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            return obj.dict()
        return obj

    @staticmethod
    def _clean_json_content(content: str) -> str:
        content_clean = content.strip()
        if content_clean.startswith("```json"):
            content_clean = content_clean[7:]
        elif content_clean.startswith("```"):
            content_clean = content_clean[3:]
        if content_clean.endswith("```"):
            content_clean = content_clean[:-3]
        content_clean = content_clean.strip()
        start = content_clean.find("{")
        end = content_clean.rfind("}")
        if start != -1 and end != -1:
            content_clean = content_clean[start : end + 1]
        return content_clean

    @staticmethod
    def _dedupe_columns(columns: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for column in columns:
            if column not in seen:
                ordered.append(column)
                seen.add(column)
        return ordered
