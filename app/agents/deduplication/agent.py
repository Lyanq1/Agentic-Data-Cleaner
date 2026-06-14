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
from langchain_core.messages import SystemMessage, ToolMessage

from app.agents.base import BaseAgent
from app.agents.deduplication.column_roles import infer_column_role
from app.agents.deduplication.models import (
    AppliedHitlResult,
    DedupDecision,
    DeduplicationHitlFeedback,
    DeduplicationAgentInput,
    FuzzyBlockingConfig,
    FuzzyCandidateSet,
    ValidatedDedupDecision,
)
from app.agents.deduplication.prompt import (
    DEDUP_DECISION_JSON_INSTRUCTION,
    build_dedup_messages,
)
from app.agents.deduplication.strategies import (
    ExactKeyDedupConfig,
    build_normalized_key_frame,
    execute_exact_key_dedup,
    execute_full_row_dedup,
    has_normalized_key_duplicates,
    run_fuzzy_blocking,
)
from app.agents.deduplication.validators import build_validation_results
from app.agents.registry import AgentRegistry
from app.agents.roles import AgentRole
from app.config.config import get_settings
from app.core.llm_factory import create_llm
from app.graphs.states.global_state import GlobalState
from app.graphs.states.output_validation import ValidationResultItem
from app.graphs.states.planning import ExecutionPlan, TaskDetail
from app.graphs.states.profiler_state import StatisticalProfile
from app.graphs.states.workers import (
    DedupPreviewGroup,
    DedupPreviewSummary,
    DeduplicationResult,
    DedupStrategyReview,
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
            existing_result = self._coerce_existing_result(state)
            hitl_feedback = self._parse_hitl_feedback(dedup_input.hitl_feedback)
            validated_decision = self._extract_debug_override_decision(dedup_input, df)
            used_debug_override = validated_decision is not None
            reused_decision = False
            if validated_decision is None:
                validated_decision = self._rebuild_decision_from_state(state, context_hash)
                reused_decision = validated_decision is not None
            if validated_decision is None:
                context = self._build_decision_context(dedup_input)
                raw_decision = await self._invoke_dedup_decision_llm(context)
                validated_decision = self._validate_dedup_decision(raw_decision, df, dedup_input)
        except Exception as exc:
            return self._failure_update(
                state,
                f"DeduplicationAgent: failed during execution: {exc}",
                failed_rules=["dedup_execution_failed"],
            )

        notes: list[str] = []
        if reused_decision:
            notes.append("Reused the previous dedup decision because the context hash matched.")
        elif used_debug_override:
            notes.append("Used the service-layer debug override instead of invoking the LLM.")

        pending_strategy_review = self._coerce_pending_strategy_review(existing_result)
        applied_hitl = None
        if hitl_feedback.key_columns is not None or hitl_feedback.keep_rule is not None or hitl_feedback.ignored_columns is not None or hitl_feedback.identifier_columns is not None:
            if pending_strategy_review is None:
                return self._failure_update(
                    state,
                    "DeduplicationAgent: received HITL feedback but no pending strategy review exists.",
                    failed_rules=["missing_pending_strategy_review"],
                )
            applied_hitl = self._apply_hitl_feedback(
                validated_decision,
                pending_strategy_review,
                hitl_feedback,
                df,
                dedup_input,
            )
            validated_decision = applied_hitl.validated_decision
            notes.extend(applied_hitl.notes)
            pending_strategy_review = applied_hitl.pending_strategy_review

        if pending_strategy_review is None:
            pending_strategy_review = self._build_strategy_review(df, validated_decision, dedup_input)

        preview_has_duplicates = pending_strategy_review.preview.duplicate_rows > 0
        should_wait_for_hitl = preview_has_duplicates and applied_hitl is None

        if should_wait_for_hitl:
            notes.append("Dedup strategy review is pending human confirmation before cleaning.")
            result = DeduplicationResult(
                applied_modes=[],
                key_columns=list(pending_strategy_review.proposed_key_columns),
                keep_strategy=pending_strategy_review.keep_rule,
                source_path=dedup_input.dataset_path,
                output_path=dedup_input.dataset_path,
                before_row_count=len(df),
                after_row_count=len(df),
                dropped_row_count=0,
                full_row_duplicate_count=0,
                key_duplicate_count=0,
                duplicate_group_count=pending_strategy_review.preview.duplicate_groups,
                notes=notes,
                decision_trace=validated_decision.to_trace(context_hash=context_hash),
                pending_strategy_review=pending_strategy_review,
            )
            worker_states = self._coerce_worker_states(state)
            worker_states.dedup_agent = WorkerStateDetail(status="done", retries=0, error_log=[])
            worker_states.last_completed_agent = self.name
            return {
                "deduplication_result": result,
                "worker_states": worker_states,
                "validation_results": build_validation_results(
                    agent_name=self.name,
                    timestamp=self._timestamp(),
                    before_row_count=len(df),
                    after_row_count=len(df),
                    decision_source=validated_decision.decision_source,
                    failed_rules=[],
                    unresolved_collisions=validated_decision.unresolved_collisions,
                    fuzzy_candidate_count=0,
                    fuzzy_notes=[],
                    pending_strategy_review=True,
                    proposed_key_columns=list(pending_strategy_review.proposed_key_columns),
                ),
                "hitl_status": "pending",
                "hitl_checkpoint": state.get("current_task_idx"),
                "current_step": "deduplication",
                "completed_steps": "deduplication",
            }

        execution = self._execute_validated_decision(df, validated_decision, dedup_input)
        notes.extend(execution["notes"])
        fuzzy_candidates = FuzzyCandidateSet()
        if dedup_input.fuzzy_enabled:
            fuzzy_candidates = self._run_fuzzy_blocking(
                execution["deduped_df"],
                validated_decision,
                dedup_input,
            )
            notes.extend(fuzzy_candidates.notes)

        failed_rules = self._validate_output(
            execution["deduped_df"],
            execution["before_row_count"],
            execution["effective_key_columns"],
            dedup_input,
        )

        output_path = self._write_output_dataframe(
            execution["deduped_df"],
            dedup_input.project_id,
        )

        if failed_rules:
            return self._failure_update(
                state,
                "DeduplicationAgent: post-dedup validation failed.",
                failed_rules=failed_rules,
            )

        result = DeduplicationResult(
            applied_modes=execution["applied_modes"],
            key_columns=execution["effective_key_columns"],
            keep_strategy=execution["keep_strategy"],
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
            pending_strategy_review=None,
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
            "validation_results": build_validation_results(
                agent_name=self.name,
                timestamp=self._timestamp(),
                before_row_count=execution["before_row_count"],
                after_row_count=execution["after_row_count"],
                decision_source=validated_decision.decision_source,
                failed_rules=[],
                unresolved_collisions=execution["unresolved_collisions"],
                fuzzy_candidate_count=fuzzy_candidates.total_count,
                fuzzy_notes=fuzzy_candidates.notes,
                pending_strategy_review=False,
                proposed_key_columns=execution["effective_key_columns"],
            ),
            "hitl_status": "approved" if applied_hitl is not None or not preview_has_duplicates else state.get("hitl_status"),
            "hitl_checkpoint": None,
            "hitl_feedback": None,
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
            fuzzy_enabled=self._should_run_fuzzy(state),
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

    def _should_run_fuzzy(self, state: GlobalState) -> bool:
        active_tasks = state.get("task_list") or []
        if "deduplication" not in active_tasks:
            return False

        planner_task = self._extract_planner_task(state.get("execution_plan"))
        if planner_task is None or planner_task.strategy is None:
            return False

        strategy = self._to_dict(planner_task.strategy) or {}
        duplicate_types = strategy.get("duplicate_types") or []
        fuzzy_matching = strategy.get("fuzzy_matching") or {}
        return (
            strategy.get("dedup_scope") == "entity_level"
            or "fuzzy_entity" in duplicate_types
            or bool(fuzzy_matching)
        )

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
                column_roles={},
                ignore_columns=[],
                decision_source="planner_fallback",
                confidence=1.0,
                reasoning_summary="Debug override was invalid, so the agent fell back to exact full-row dedup.",
                validation_notes=["Debug override supplied no usable key columns."],
                unresolved_collisions=[],
            )

        return ValidatedDedupDecision(
            mode="exact_key",
            key_columns=key_columns,
            column_roles=self._resolve_column_roles(key_columns, dedup_input),
            ignore_columns=[],
            decision_source="planner_fallback",
            confidence=1.0,
            reasoning_summary="Used the service-layer debug override for key-based dedup testing.",
            validation_notes=["Debug override applied at the service layer."],
            unresolved_collisions=[],
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
            "available_column_roles": ["phone", "email", "address", "company_name", "person_name"],
            "pk_candidates": statistical_profile.get("pk_candidates", []),
            "near_unique_columns": statistical_profile.get("near_unique_columns", []),
            "high_null_columns": statistical_profile.get("high_null_columns", []),
            "planner_task": planner_task,
            "suggested_candidate_sets": self._build_suggested_candidate_sets(dedup_input),
            "fuzzy_enabled": dedup_input.fuzzy_enabled,
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
            logger.warning("DeduplicationAgent: failed to parse LLM decision, using exact_full_row fallback. error=%s", exc)
            return DedupDecision(
                mode="exact_full_row",
                key_columns=[],
                column_roles={},
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
        sanitized_llm_roles = self._sanitize_llm_column_roles(
            decision.column_roles,
            df.columns,
            dedup_input,
        )
        requested = self._dedupe_columns(
            [column for column in decision.key_columns if column not in set(decision.ignore_columns)]
        )
        resolved_column_roles = self._resolve_column_roles(
            requested,
            dedup_input,
            llm_roles=sanitized_llm_roles,
        )
        missing = [column for column in requested if column not in df.columns]
        if missing:
            return self._fallback_decision(
                df,
                dedup_input,
                column_roles=sanitized_llm_roles,
                validation_notes=[f"LLM selected missing columns: {missing}"],
                reasoning_summary=decision.reasoning_summary or "The LLM selected invalid columns.",
            )

        filtered = list(requested)
        removed_high_null = [column for column in filtered if null_rates.get(column, 0.0) > 0.30]
        filtered = [column for column in filtered if column not in removed_high_null]
        validation_notes: list[str] = []
        unresolved_collisions: list[dict[str, Any]] = []
        if removed_high_null:
            validation_notes.append(
                f"Removed high-null key columns from the LLM decision: {removed_high_null}."
            )
        if decision.mode == "exact_key" and not filtered:
            return self._fallback_decision(
                df,
                dedup_input,
                column_roles=sanitized_llm_roles,
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
                column_roles=sanitized_llm_roles,
                ignore_columns=list(decision.ignore_columns),
                decision_source="safe_default",
                confidence=decision.confidence,
                reasoning_summary=decision.reasoning_summary or "Technical row identifiers are not used as the only dedup key.",
                validation_notes=validation_notes,
                unresolved_collisions=[],
            )
        if decision.mode == "exact_key" and all(null_rates.get(column, 0.0) > 0.80 for column in filtered):
            return self._fallback_decision(
                df,
                dedup_input,
                column_roles=sanitized_llm_roles,
                validation_notes=validation_notes + ["All candidate key columns were null in more than 80% of rows."],
                reasoning_summary=decision.reasoning_summary or "The LLM key set was too sparse to trust.",
            )

        if decision.mode == "exact_key":
            if self._is_name_only_key(filtered, dedup_input, column_roles=resolved_column_roles):
                unresolved_count = self._count_name_only_collision_rows(df, filtered)
                unresolved_collisions.append(
                    {
                        "collision_type": "name_only",
                        "affected_row_count": unresolved_count,
                        "key_columns": list(filtered),
                    }
                )
                validation_notes.append(
                    f"Key set {filtered} contains only name-like columns with no hard identifier; skipped auto-merge."
                )
                return self._fallback_decision(
                    df,
                    dedup_input,
                    column_roles=sanitized_llm_roles,
                    validation_notes=validation_notes,
                    reasoning_summary=decision.reasoning_summary or "Name-only keys are not safe for automatic deduplication.",
                    unresolved_collisions=unresolved_collisions,
                )
            if len(filtered) == 1 and self._is_weak_single_key(filtered[0], dedup_input, column_roles=resolved_column_roles):
                unresolved_collisions.append(
                    {
                        "collision_type": "weak_phone_only"
                        if self._looks_like_phone_identifier(
                            filtered[0],
                            dedup_input,
                            column_roles=resolved_column_roles,
                        )
                        else "weak_single_key",
                        "affected_row_count": self._count_duplicate_rows(df, filtered),
                        "key_columns": list(filtered),
                    }
                )
                validation_notes.append(
                    f"Single-column key '{filtered[0]}' is a weak identifier; skipped auto-merge."
                )
                return self._fallback_decision(
                    df,
                    dedup_input,
                    column_roles=sanitized_llm_roles,
                    validation_notes=validation_notes,
                    reasoning_summary=decision.reasoning_summary or "Weak single-field keys are not safe for automatic deduplication.",
                    unresolved_collisions=unresolved_collisions,
                )
            if decision.confidence is not None and decision.confidence < 0.6:
                validation_notes.append("LLM confidence was below 0.6; proceeding because the key set passed deterministic validation.")
            return ValidatedDedupDecision(
                mode="exact_key",
                key_columns=filtered,
                column_roles=sanitized_llm_roles,
                ignore_columns=list(decision.ignore_columns),
                decision_source="llm",
                confidence=decision.confidence,
                reasoning_summary=decision.reasoning_summary,
                validation_notes=validation_notes,
                unresolved_collisions=unresolved_collisions,
            )

        if decision.confidence is not None and decision.confidence < 0.6:
            validation_notes.append("LLM confidence was below 0.6; proceeding with exact full-row dedup.")
        return ValidatedDedupDecision(
            mode="exact_full_row",
            key_columns=[],
            column_roles=sanitized_llm_roles,
            ignore_columns=list(decision.ignore_columns),
            decision_source="llm",
            confidence=decision.confidence,
            reasoning_summary=decision.reasoning_summary,
            validation_notes=validation_notes,
            unresolved_collisions=[],
        )

    def _fallback_decision(
        self,
        df: pd.DataFrame,
        dedup_input: DeduplicationAgentInput,
        *,
        column_roles: dict[str, str] | None,
        validation_notes: list[str],
        reasoning_summary: str,
        unresolved_collisions: list[dict[str, Any]] | None = None,
    ) -> ValidatedDedupDecision:
        unresolved_collisions = unresolved_collisions or []
        planner_task = dedup_input.planner_task
        if planner_task:
            strategy = self._to_dict(planner_task.strategy) or {}
            primary_keys = self._dedupe_columns(strategy.get("primary_keys") or [])
            planner_primary_roles = self._resolve_column_roles(primary_keys, dedup_input)
            if primary_keys and not self._is_name_only_key(primary_keys, dedup_input, column_roles=planner_primary_roles) and self._candidate_has_duplicates(df, primary_keys, dedup_input):
                return ValidatedDedupDecision(
                    mode="exact_key",
                    key_columns=primary_keys,
                    column_roles=self._merge_column_roles(column_roles, planner_primary_roles),
                    ignore_columns=[],
                    decision_source="planner_fallback",
                    confidence=None,
                    reasoning_summary=reasoning_summary,
                    validation_notes=validation_notes + ["Used planner strategy.primary_keys as fallback."],
                    unresolved_collisions=unresolved_collisions,
                )
            planner_columns = self._dedupe_columns(planner_task.columns)
            planner_column_roles = self._resolve_column_roles(planner_columns, dedup_input)
            if planner_columns and not self._is_name_only_key(planner_columns, dedup_input, column_roles=planner_column_roles) and self._candidate_has_duplicates(df, planner_columns, dedup_input):
                return ValidatedDedupDecision(
                    mode="exact_key",
                    key_columns=planner_columns,
                    column_roles=self._merge_column_roles(column_roles, planner_column_roles),
                    ignore_columns=[],
                    decision_source="planner_fallback",
                    confidence=None,
                    reasoning_summary=reasoning_summary,
                    validation_notes=validation_notes + ["Used planner task columns as fallback."],
                    unresolved_collisions=unresolved_collisions,
                )

        if dedup_input.statistical_profile:
            candidate_sets: list[list[str]] = []
            for column in dedup_input.statistical_profile.near_unique_columns:
                candidate_sets.append([column])
            for column in dedup_input.statistical_profile.pk_candidates:
                candidate_sets.append([column])

            for candidate in candidate_sets:
                candidate_roles = self._resolve_column_roles(candidate, dedup_input)
                if self._candidate_has_duplicates(df, candidate, dedup_input):
                    return ValidatedDedupDecision(
                        mode="exact_key",
                        key_columns=candidate,
                        column_roles=self._merge_column_roles(column_roles, candidate_roles),
                        ignore_columns=[],
                        decision_source="profile_fallback",
                        confidence=None,
                        reasoning_summary=reasoning_summary,
                        validation_notes=validation_notes + [f"Used statistical profile candidate {candidate} as fallback."],
                        unresolved_collisions=unresolved_collisions,
                    )

        return ValidatedDedupDecision(
            mode="exact_full_row",
            key_columns=[],
            column_roles=dict(column_roles or {}),
            ignore_columns=[],
            decision_source="safe_default",
            confidence=None,
            reasoning_summary=reasoning_summary,
            validation_notes=validation_notes + ["Fell back to exact full-row dedup."],
            unresolved_collisions=unresolved_collisions,
        )

    def _execute_validated_decision(
        self,
        df: pd.DataFrame,
        validated_decision: ValidatedDedupDecision,
        dedup_input: DeduplicationAgentInput,
    ) -> dict[str, Any]:
        full_row_result = execute_full_row_dedup(df)
        before_row_count = int(full_row_result["before_row_count"])
        deduped_df = full_row_result["deduped_df"]
        full_row_duplicate_count = int(full_row_result["full_row_duplicate_count"])

        applied_modes: list[str] = []
        notes: list[str] = [
            f"Decision source: {validated_decision.decision_source}.",
            f"Decision rationale: {validated_decision.reasoning_summary}",
        ]
        if validated_decision.validation_notes:
            notes.extend(validated_decision.validation_notes)
        for collision in validated_decision.unresolved_collisions:
            collision_type = collision.get("collision_type", "unknown")
            affected_rows = collision.get("affected_row_count", 0)
            key_columns = collision.get("key_columns", [])
            if collision_type == "weak_phone_only":
                notes.append(
                    f"Weak-key collision detected on {key_columns or ['phone']}. {affected_rows} row(s) were not merged."
                )
            elif collision_type == "cross_script_name_only":
                notes.append(
                    f"Cross-script name-only similarity detected on {key_columns}. {affected_rows} row(s) were not merged."
                )
            elif collision_type == "name_only":
                notes.append(
                    f"Name-only key collision detected on {key_columns}. {affected_rows} row(s) were not merged."
                )

        if full_row_duplicate_count > 0:
            applied_modes.append("exact_full_row")
            notes.append(
                f"Removed {full_row_duplicate_count} exact full-row duplicate rows using keep='first'."
            )

        key_duplicate_count = 0
        duplicate_group_count = int(full_row_result["duplicate_group_count"])
        keep_strategy = validated_decision.keep_rule if validated_decision.mode == "exact_key" else "keep_first"
        effective_key_columns: list[str] = []
        unresolved_collisions = list(validated_decision.unresolved_collisions)
        if validated_decision.mode == "exact_key" and validated_decision.key_columns:
            key_execution = execute_exact_key_dedup(
                deduped_df,
                ExactKeyDedupConfig(
                    key_columns=validated_decision.key_columns,
                    column_roles=validated_decision.column_roles,
                    semantic_profile=dedup_input.semantic_profile,
                    statistical_profile=dedup_input.statistical_profile,
                    keep_rule=validated_decision.keep_rule,
                    notes=[],
                    unresolved_collisions=unresolved_collisions,
                ),
            )
            key_duplicate_count = key_execution.key_duplicate_count
            if key_duplicate_count > 0:
                deduped_df = key_execution.deduped_df
                duplicate_group_count = key_execution.duplicate_group_count
                keep_strategy = key_execution.kept_strategy
                effective_key_columns = list(validated_decision.key_columns)
                unresolved_collisions = key_execution.unresolved_collisions
                applied_modes.append("exact_key")
                notes.extend(key_execution.notes)
                notes.append(
                    "Removed "
                    f"{key_duplicate_count} key-based duplicate rows on {validated_decision.key_columns} "
                    f"using keep='{keep_strategy}'."
                )
            else:
                notes.extend(key_execution.notes)
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
            "keep_strategy": keep_strategy,
            "effective_key_columns": effective_key_columns,
            "unresolved_collisions": unresolved_collisions,
            "notes": notes,
        }

    @staticmethod
    def _coerce_existing_result(state: GlobalState) -> DeduplicationResult | None:
        existing = state.get("deduplication_result")
        if not existing:
            return None
        return DeduplicationResult.model_validate(existing)

    def _parse_hitl_feedback(self, raw_feedback: str | None) -> DeduplicationHitlFeedback:
        if not raw_feedback:
            return DeduplicationHitlFeedback()
        try:
            return DeduplicationHitlFeedback.model_validate_json(raw_feedback)
        except Exception as exc:
            logger.warning("DeduplicationAgent: ignoring invalid hitl_feedback payload: %s", exc)
            return DeduplicationHitlFeedback()

    @staticmethod
    def _coerce_pending_strategy_review(
        existing_result: DeduplicationResult | None,
    ) -> DedupStrategyReview | None:
        if existing_result is None:
            return None
        return existing_result.pending_strategy_review

    def _build_strategy_review(
        self,
        df: pd.DataFrame,
        validated_decision: ValidatedDedupDecision,
        dedup_input: DeduplicationAgentInput,
    ) -> DedupStrategyReview:
        proposed_key_columns = list(validated_decision.key_columns)
        suggested_identifier_columns = self._suggested_identifier_columns(dedup_input)
        ignored_columns = [
            column
            for column in (dedup_input.dataset_schema or {}).keys()
            if self._looks_like_technical_id(column, dedup_input)
        ]
        warnings = list(validated_decision.validation_notes)
        preview = self._build_preview_summary(
            df,
            validated_decision,
            dedup_input,
        )
        if validated_decision.unresolved_collisions:
            warnings.extend(
                self._collision_rationale(collision.get("collision_type"), collision.get("key_columns") or proposed_key_columns)
                for collision in validated_decision.unresolved_collisions
            )
        questions = [
            "Which columns should define the same entity?",
            "Which columns should be treated as reliable identifiers?",
            "Which columns should be ignored because they are technical or not trustworthy for deduplication?",
            "How should one row be kept from each duplicate group?",
        ]
        return DedupStrategyReview(
            proposed_mode=validated_decision.mode,
            proposed_key_columns=proposed_key_columns,
            suggested_identifier_columns=suggested_identifier_columns,
            ignored_columns=ignored_columns,
            keep_rule=validated_decision.keep_rule,
            questions=questions,
            warnings=self._dedupe_strings(warnings),
            preview=preview,
        )

    def _build_preview_summary(
        self,
        df: pd.DataFrame,
        validated_decision: ValidatedDedupDecision,
        dedup_input: DeduplicationAgentInput,
    ) -> DedupPreviewSummary:
        if validated_decision.mode == "exact_key" and validated_decision.key_columns:
            normalized_keys = build_normalized_key_frame(
                df,
                validated_decision.key_columns,
                explicit_roles=validated_decision.column_roles,
                semantic_profile=dedup_input.semantic_profile,
            )
            working = df.join(normalized_keys)
            compare_columns = list(normalized_keys.columns)
            duplicate_mask = working.duplicated(subset=compare_columns, keep=False)
            duplicate_rows = int(working.duplicated(subset=compare_columns, keep="first").sum())
            duplicate_group_count = self._count_duplicate_groups(working.loc[duplicate_mask], compare_columns)
            sample_groups: list[DedupPreviewGroup] = []
            if duplicate_mask.any():
                grouped = working.loc[duplicate_mask].groupby(compare_columns, dropna=False)
                for _, group in grouped:
                    if len(sample_groups) >= 5:
                        break
                    sample_rows = []
                    for _, row in df.loc[group.index].head(2).iterrows():
                        sample_rows.append(
                            {
                                column: self._json_safe_value(row[column])
                                for column in self._preview_visible_columns(validated_decision.key_columns, df.columns)
                            }
                        )
                    group_key = {
                        column: self._json_safe_value(group.iloc[0][compare_name])
                        for column, compare_name in zip(validated_decision.key_columns, compare_columns, strict=False)
                    }
                    sample_groups.append(
                        DedupPreviewGroup(
                            group_key=group_key,
                            row_count=int(len(group)),
                            sample_rows=sample_rows,
                        )
                    )
            return DedupPreviewSummary(
                duplicate_rows=duplicate_rows,
                duplicate_groups=duplicate_group_count,
                sample_groups=sample_groups,
            )

        full_row_result = execute_full_row_dedup(df)
        return DedupPreviewSummary(
            duplicate_rows=int(full_row_result["full_row_duplicate_count"]),
            duplicate_groups=int(full_row_result["duplicate_group_count"]),
            sample_groups=[],
        )

    def _apply_hitl_feedback(
        self,
        validated_decision: ValidatedDedupDecision,
        pending_strategy_review: DedupStrategyReview,
        hitl_feedback: DeduplicationHitlFeedback,
        df: pd.DataFrame,
        dedup_input: DeduplicationAgentInput,
    ) -> AppliedHitlResult:
        requested_key_columns = self._dedupe_columns(
            list(hitl_feedback.key_columns or pending_strategy_review.proposed_key_columns)
        )
        ignored_columns = self._dedupe_columns(
            list(hitl_feedback.ignored_columns or pending_strategy_review.ignored_columns)
        )
        requested_key_columns = [column for column in requested_key_columns if column not in set(ignored_columns)]
        missing_columns = [column for column in requested_key_columns if column not in df.columns]
        if missing_columns:
            raise ValueError(f"HITL feedback selected unknown key columns: {missing_columns}")

        keep_rule = hitl_feedback.keep_rule or pending_strategy_review.keep_rule
        resolved_roles = self._resolve_column_roles(
            requested_key_columns,
            dedup_input,
            llm_roles=validated_decision.column_roles,
        )
        updated_decision = ValidatedDedupDecision(
            mode="exact_key" if requested_key_columns else "exact_full_row",
            key_columns=requested_key_columns,
            column_roles=resolved_roles,
            ignore_columns=ignored_columns,
            decision_source=validated_decision.decision_source,
            confidence=validated_decision.confidence,
            reasoning_summary=validated_decision.reasoning_summary,
            keep_rule=keep_rule,
            validation_notes=list(validated_decision.validation_notes),
            unresolved_collisions=list(validated_decision.unresolved_collisions),
        )
        notes = ["Applied human-reviewed dedup strategy before cleaning."]
        if hitl_feedback.identifier_columns:
            notes.append(
                "Human confirmed identifier columns: "
                + ", ".join(self._dedupe_columns(hitl_feedback.identifier_columns))
                + "."
            )
        if hitl_feedback.note:
            notes.append(f"Human note: {hitl_feedback.note}")
        return AppliedHitlResult(
            validated_decision=updated_decision,
            notes=notes,
            pending_strategy_review=None,
        )

    def _suggested_identifier_columns(self, dedup_input: DeduplicationAgentInput) -> list[str]:
        available_columns = list((dedup_input.dataset_schema or {}).keys())
        return [
            column
            for column in available_columns
            if self._is_hard_identifier_column(column, dedup_input)
        ][:8]

    @staticmethod
    def _preview_visible_columns(key_columns: list[str], available_columns: Any) -> list[str]:
        visible = list(key_columns)
        for column in available_columns:
            if column in visible:
                continue
            visible.append(column)
            if len(visible) >= max(3, len(key_columns) + 2):
                break
        return visible

    @staticmethod
    def _collision_rationale(collision_type: str | None, key_columns: list[str]) -> str:
        if collision_type == "name_only":
            return f"Rows matched on name-like fields {key_columns} without a hard identifier."
        if collision_type == "weak_phone_only":
            return f"Rows matched on phone-like field {key_columns}, which may be shared or reused."
        return f"Rows matched on weak key fields {key_columns} and were not auto-merged."

    @staticmethod
    def _dedupe_strings(values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            if value and value not in seen:
                ordered.append(value)
                seen.add(value)
        return ordered

    @staticmethod
    def _fingerprint_row(row: pd.Series) -> str:
        payload = {
            str(column): DeduplicationAgent._json_safe_value(value)
            for column, value in row.items()
        }
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _json_safe_value(value: Any) -> Any:
        if pd.isna(value):
            return None
        if hasattr(value, "item"):
            try:
                return value.item()
            except Exception:
                return str(value)
        return value

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
            column_roles=dict(trace.column_roles),
            ignore_columns=list(trace.ignore_columns),
            decision_source=trace.decision_source,
            confidence=trace.confidence,
            reasoning_summary=trace.reasoning_summary,
            keep_rule=result.keep_strategy if result.keep_strategy in {"keep_most_complete", "keep_first", "keep_last"} else "keep_most_complete",
            validation_notes=list(trace.validation_notes),
            unresolved_collisions=[],
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

    def _candidate_has_duplicates(
        self,
        df: pd.DataFrame,
        columns: list[str],
        dedup_input: DeduplicationAgentInput,
    ) -> bool:
        if not columns or any(column not in df.columns for column in columns):
            return False
        return has_normalized_key_duplicates(
            df,
            columns,
            explicit_roles=self._resolve_column_roles(columns, dedup_input),
            semantic_profile=dedup_input.semantic_profile,
        )

    def _run_fuzzy_blocking(
        self,
        df: pd.DataFrame,
        validated_decision: ValidatedDedupDecision,
        dedup_input: DeduplicationAgentInput,
    ) -> FuzzyCandidateSet:
        return run_fuzzy_blocking(
            df,
            key_columns=validated_decision.key_columns,
            ignore_columns=validated_decision.ignore_columns,
            column_roles=validated_decision.column_roles,
            semantic_profile=dedup_input.semantic_profile,
            config=FuzzyBlockingConfig(),
        )

    @staticmethod
    def _count_duplicate_rows(df: pd.DataFrame, key_columns: list[str]) -> int:
        if not key_columns or any(column not in df.columns for column in key_columns):
            return 0
        return int(df.duplicated(subset=key_columns, keep=False).sum())

    def _count_name_only_collision_rows(self, df: pd.DataFrame, key_columns: list[str]) -> int:
        return self._count_duplicate_rows(df, key_columns)

    def _resolve_column_roles(
        self,
        columns: list[str],
        dedup_input: DeduplicationAgentInput,
        *,
        llm_roles: dict[str, str] | None = None,
    ) -> dict[str, str]:
        resolved: dict[str, str] = {}
        for column in columns:
            role = infer_column_role(
                column,
                explicit_roles=llm_roles,
                semantic_profile=dedup_input.semantic_profile,
            )
            if role is not None:
                resolved[column] = role
        return resolved

    @staticmethod
    def _merge_column_roles(
        primary: dict[str, str] | None,
        secondary: dict[str, str] | None,
    ) -> dict[str, str]:
        merged = dict(primary or {})
        merged.update(secondary or {})
        return merged

    def _sanitize_llm_column_roles(
        self,
        llm_roles: dict[str, str] | None,
        available_columns: Any,
        dedup_input: DeduplicationAgentInput,
    ) -> dict[str, str]:
        sanitized: dict[str, str] = {}
        if not llm_roles:
            return sanitized
        available = set(available_columns)
        for column, role_name in llm_roles.items():
            if column not in available:
                continue
            role = infer_column_role(
                column,
                explicit_roles={column: role_name},
                semantic_profile=dedup_input.semantic_profile,
            )
            if role is not None:
                sanitized[column] = role
        return sanitized

    def _is_name_only_key(
        self,
        key_columns: list[str],
        dedup_input: DeduplicationAgentInput,
        *,
        column_roles: dict[str, str] | None = None,
    ) -> bool:
        if not key_columns:
            return False
        if not all(self._is_name_like_column(column, dedup_input, column_roles=column_roles) for column in key_columns):
            return False
        return not any(
            self._is_hard_identifier_column(column, dedup_input, column_roles=column_roles)
            for column in key_columns
        )

    def _is_name_like_column(
        self,
        column_name: str,
        dedup_input: DeduplicationAgentInput,
        *,
        column_roles: dict[str, str] | None = None,
    ) -> bool:
        role = infer_column_role(
            column_name,
            explicit_roles=column_roles,
            semantic_profile=dedup_input.semantic_profile,
        )
        return role in {"company_name", "person_name"}

    def _is_hard_identifier_column(
        self,
        column_name: str,
        dedup_input: DeduplicationAgentInput,
        *,
        column_roles: dict[str, str] | None = None,
    ) -> bool:
        role = infer_column_role(
            column_name,
            explicit_roles=column_roles,
            semantic_profile=dedup_input.semantic_profile,
        )
        if role in {"phone", "email"}:
            return True
        profile = dedup_input.semantic_profile.columns.get(column_name) if dedup_input.semantic_profile else None
        if profile:
            logical_group = profile.logical_group.casefold()
            description = profile.description.casefold()
            relationship_text = " ".join(profile.relationships).casefold()
            if logical_group in {"identity", "identifier"} and not self._looks_like_technical_id(column_name, dedup_input):
                return True
            semantic_evidence = " ".join([description, relationship_text, profile.expected_type_reason.casefold()])
            if "unique identifier" in semantic_evidence or "business identifier" in semantic_evidence:
                return True
        stat_column = self._get_statistical_column(dedup_input, column_name)
        if stat_column and stat_column.unique_ratio >= 0.98 and stat_column.null_rate <= 0.05:
            return not self._looks_like_technical_id(column_name, dedup_input)
        return False

    def _looks_like_phone_identifier(
        self,
        column_name: str,
        dedup_input: DeduplicationAgentInput,
        *,
        column_roles: dict[str, str] | None = None,
    ) -> bool:
        role = infer_column_role(
            column_name,
            explicit_roles=column_roles,
            semantic_profile=dedup_input.semantic_profile,
        )
        return role == "phone"

    def _is_weak_single_key(
        self,
        column_name: str,
        dedup_input: DeduplicationAgentInput,
        *,
        column_roles: dict[str, str] | None = None,
    ) -> bool:
        return not self._is_hard_identifier_column(column_name, dedup_input, column_roles=column_roles)

    def _validate_output(
        self,
        deduped_df: pd.DataFrame,
        before_row_count: int,
        key_columns: list[str],
        dedup_input: DeduplicationAgentInput,
    ) -> list[str]:
        failed_rules: list[str] = []
        if len(deduped_df) > before_row_count:
            failed_rules.append("row_count_increased_after_dedup")
        if deduped_df.duplicated(keep=False).any():
            failed_rules.append("exact_full_row_duplicates_still_present")
        if key_columns and has_normalized_key_duplicates(
            deduped_df,
            key_columns,
            explicit_roles=self._resolve_column_roles(key_columns, dedup_input),
            semantic_profile=dedup_input.semantic_profile,
        ):
            failed_rules.append("key_duplicates_still_present")
        return failed_rules

    @staticmethod
    def _get_statistical_column(
        dedup_input: DeduplicationAgentInput,
        column_name: str,
    ) -> Any | None:
        profile = dedup_input.statistical_profile
        if not profile:
            return None
        for column in profile.columns:
            if column.column_name == column_name:
                return column
        return None

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
            "fuzzy_enabled": dedup_input.fuzzy_enabled,
        }
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _column_null_rates(profile: StatisticalProfile | None) -> dict[str, float]:
        if not profile:
            return {}
        return {column.column_name: float(column.null_rate) for column in profile.columns}

    def _build_suggested_candidate_sets(self, dedup_input: DeduplicationAgentInput) -> list[list[str]]:
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
        profile = dedup_input.semantic_profile.columns.get(column_name) if dedup_input.semantic_profile else None
        if profile:
            semantic_evidence = " ".join(
                [
                    profile.description.casefold(),
                    profile.logical_group.casefold(),
                    profile.expected_type_reason.casefold(),
                    profile.allow_missing_reason.casefold(),
                    (profile.error_reason or "").casefold(),
                ]
            )
            if any(
                marker in semantic_evidence
                for marker in ["record identifier", "row identifier", "surrogate key", "technical identifier"]
            ):
                return True
            if profile.logical_group.casefold() == "identity" and "each record" in semantic_evidence:
                return True
        if normalized in {"id", "_id", "row_id", "record_id"}:
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
