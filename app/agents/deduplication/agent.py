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
from app.agents.deduplication.column_roles import (
    descriptor_is_hard_identifier,
    descriptor_is_name_like,
    infer_column_semantics,
    resolve_name_family,
)
from app.agents.deduplication.models import (
    BlockKeySpec,
    BlockingSpec,
    ColumnSemanticDescriptor,
    DedupDecision,
    DeduplicationAgentInput,
    EvidenceSpec,
    FuzzyBlockingConfig,
    FuzzyCandidateSet,
    FuzzyExecutionPlan,
    ValidatedDedupDecision,
)
from app.agents.deduplication.prompt import (
    DEDUP_DECISION_JSON_INSTRUCTION,
    build_dedup_messages,
)
from app.agents.deduplication.strategies import (
    ExactKeyDedupConfig,
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
from app.graphs.states.planning import TaskDetail
from app.graphs.states.profiler_state import StatisticalProfile
from app.graphs.states.workers import (
    DeduplicationResult,
    WorkerStateDetail,
    WorkerStates,
)
from app.graphs.utils import _load_latest_dataframe_with_source, _resolve_active_task
from app.tools.data.dedup import inspect_duplicate_candidates, profile_fuzzy_columns

logger = logging.getLogger(__name__)


@AgentRegistry.auto_register
class DeduplicationAgent(BaseAgent):
    """Choose a dedup strategy with the LLM, then execute it deterministically."""

    name = AgentRole.DEDUP_AGENT.value
    description = (
        "Selects a deduplication strategy with tool-assisted LLM reasoning, then runs "
        "exact full-row and exact key-based deduplication deterministically."
    )
    tools = [inspect_duplicate_candidates, profile_fuzzy_columns]

    def __init__(self) -> None:
        super().__init__()
        self.json_llm = create_llm()
        self._tool_map = {tool.name: tool for tool in self.tools}

    async def run(self, state: GlobalState) -> dict[str, Any]:
        planner_task = _resolve_active_task(state)
        if planner_task is None or planner_task.task_id != "deduplication":
            return self._failure_update(
                state,
                "DeduplicationAgent: active task is not deduplication.",
                failed_rules=["active_task_mismatch"],
            )
        df, source_path = _load_latest_dataframe_with_source(state, planner_task)
        if df is None or not source_path:
            return self._failure_update(
                state,
                "DeduplicationAgent: no approved lineage version or readable dataframe path found in state.",
                failed_rules=["missing_dataset_path"],
            )

        dedup_input = self._build_input(state, source_path, planner_task=planner_task)
        logger.info(
            "DeduplicationAgent: starting | source_path=%s | project_id=%s",
            dedup_input.dataset_path,
            dedup_input.project_id,
        )

        try:
            context_hash = self._compute_context_hash(dedup_input)
            validated_decision = None
            reused_decision = False
            used_planner_strategy = False
            if validated_decision is None:
                validated_decision = self._rebuild_decision_from_state(state, context_hash)
                reused_decision = validated_decision is not None
            if validated_decision is None:
                validated_decision = self._build_planner_owned_decision(df, dedup_input)
                used_planner_strategy = validated_decision is not None
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
        elif used_planner_strategy:
            notes.append("Used the planner-approved dedup strategy as the primary execution input.")

        # ── TRACE ─────────────────────────────────────────────────────────────
        print("[DEDUP_TRACE] ── DECISION ──────────────────────────────────────────")
        print(f"[DEDUP_TRACE] source       : {'reused_from_state' if reused_decision else 'planner_strategy' if used_planner_strategy else 'llm'}")
        print(f"[DEDUP_TRACE] mode         : {validated_decision.mode}")
        print(f"[DEDUP_TRACE] key_columns  : {validated_decision.key_columns}")
        print(f"[DEDUP_TRACE] ignore_cols  : {validated_decision.ignore_columns}")
        print(f"[DEDUP_TRACE] keep_rule    : {validated_decision.keep_rule}")
        print(f"[DEDUP_TRACE] fuzzy_enabled: {dedup_input.fuzzy_enabled}")
        _fplan = validated_decision.fuzzy_plan
        print(f"[DEDUP_TRACE] fuzzy_plan   : {'ENABLED, specs=' + str(len(_fplan.blocking_specs)) if _fplan and _fplan.enabled else 'DISABLED or None'}")
        if _fplan and _fplan.enabled:
            for _s in _fplan.blocking_specs:
                print(f"[DEDUP_TRACE]   blocking_spec: id={_s.spec_id}, cols={_s.target_columns}, threshold={_s.similarity_threshold}")
            for _e in _fplan.evidence_specs:
                print(f"[DEDUP_TRACE]   evidence_spec: support={_e.support_columns}, reject={_e.reject_columns}, hard_reject={_e.hard_reject_on_conflict}")
        print(f"[DEDUP_TRACE] input rows   : {len(df)}")
        # ──────────────────────────────────────────────────────────────────────

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

            # ── TRACE: STEP 3a – Fuzzy candidates ────────────────────────────
            _by_res: dict[str, int] = {}
            for _c in fuzzy_candidates.candidates:
                _by_res[_c.resolution] = _by_res.get(_c.resolution, 0) + 1
            print("[DEDUP_TRACE] ── STEP 3: fuzzy blocking ──────────────────────")
            print(f"[DEDUP_TRACE]   total candidates: {len(fuzzy_candidates.candidates)}")
            print(f"[DEDUP_TRACE]   by resolution   : {_by_res}")
            if "ProviderNumber" in execution["deduped_df"].columns:
                print(f"[DEDUP_TRACE]   10018 rows before fuzzy merge: {int((execution['deduped_df']['ProviderNumber'].astype(str) == '10018').sum())}")
            # ──────────────────────────────────────────────────────────────────

            dropped_fuzzy_indices = set()
            for cand in fuzzy_candidates.candidates:
                if cand.resolution != "supported":
                    continue
                if cand.row_index_a in dropped_fuzzy_indices or cand.row_index_b in dropped_fuzzy_indices:
                    continue
                row_a = execution["deduped_df"].loc[cand.row_index_a]
                row_b = execution["deduped_df"].loc[cand.row_index_b]
                nulls_a = row_a.isna().sum()
                nulls_b = row_b.isna().sum()

                if execution["keep_strategy"] == "keep_first":
                    drop_idx = max(cand.row_index_a, cand.row_index_b)
                elif execution["keep_strategy"] == "keep_last":
                    drop_idx = min(cand.row_index_a, cand.row_index_b)
                else:
                    if nulls_b > nulls_a:
                        drop_idx = cand.row_index_b
                    elif nulls_a > nulls_b:
                        drop_idx = cand.row_index_a
                    else:
                        drop_idx = max(cand.row_index_a, cand.row_index_b)

                # Per-pair trace (only log if a watched provider is involved)
                _pn_col = "ProviderNumber"
                if _pn_col in execution["deduped_df"].columns:
                    _pa = execution["deduped_df"].at[cand.row_index_a, _pn_col]
                    _pb = execution["deduped_df"].at[cand.row_index_b, _pn_col]
                    print(f"[DEDUP_TRACE]   drop pair ({cand.row_index_a}[{_pa}], {cand.row_index_b}[{_pb}]) score={cand.similarity_score:.2f} field={cand.field} → DROP idx={drop_idx}")

                dropped_fuzzy_indices.add(drop_idx)

            if dropped_fuzzy_indices:
                execution["deduped_df"] = execution["deduped_df"].drop(index=list(dropped_fuzzy_indices))
                notes.append(f"Auto-merged {len(dropped_fuzzy_indices)} fuzzy duplicate rows.")
                execution["after_row_count"] = len(execution["deduped_df"])
                execution["dropped_row_count"] += len(dropped_fuzzy_indices)

            # ── TRACE: STEP 3b – After fuzzy merge ────────────────────────────
            print("[DEDUP_TRACE] ── STEP 3 RESULT: after fuzzy merge ─────────────")
            print(f"[DEDUP_TRACE]   dropped {len(dropped_fuzzy_indices)} rows, total now={len(execution['deduped_df'])}")
            if "ProviderNumber" in execution["deduped_df"].columns:
                _pn3 = execution["deduped_df"]["ProviderNumber"].astype(str)
                print(f"[DEDUP_TRACE]   10018 rows after fuzzy merge: {int((_pn3 == '10018').sum())}")
                _lost3 = set(execution["deduped_df"]["ProviderNumber"].dropna().unique())
            # ──────────────────────────────────────────────────────────────────


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
        )

        worker_states = self._coerce_worker_states(state)
        worker_states.dedup_agent = WorkerStateDetail(status="done", retries=0, error_log=[])
        worker_states.last_completed_agent = self.name
        worker_outputs = dict(state.get("worker_outputs") or {})
        worker_outputs[self.name] = result.model_dump(mode="json")

        logger.info(
            "DeduplicationAgent: completed | output_path=%s | before_rows=%s | after_rows=%s | modes=%s | source=%s",
            output_path,
            execution["before_row_count"],
            execution["after_row_count"],
            execution["applied_modes"],
            validated_decision.decision_source,
        )

        return {
            "worker_outputs": worker_outputs,
            "physical_dataframe_path": output_path,
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
            ),
            "hitl_status": state.get("hitl_status"),
            "hitl_checkpoint": None,
            "current_step": "deduplication",
            "completed_steps": "deduplication",
        }

    def _build_input(
        self,
        state: GlobalState,
        dataset_path: str,
        *,
        planner_task: TaskDetail | None = None,
    ) -> DeduplicationAgentInput:
        return DeduplicationAgentInput(
            project_id=state.get("project_id"),
            dataset_path=dataset_path,
            dataset_schema=state.get("dataset_schema"),
            user_prompt=state.get("user_prompt"),
            statistical_profile=state.get("statistical_profile"),
            semantic_profile=state.get("semantic_profile"),
            planner_task=planner_task,
            retry_count=state.get("retry_count") or 0,
            fuzzy_enabled=self._should_run_fuzzy(state, planner_task),
        )

    def _should_run_fuzzy(self, state: GlobalState, planner_task: TaskDetail | None) -> bool:
        active_tasks = state.get("task_list") or []
        if "deduplication" not in active_tasks:
            return False

        if planner_task is None or planner_task.strategy is None:
            return False

        strategy = self._to_dict(planner_task.strategy) or {}
        duplicate_types = strategy.get("duplicate_types") or []
        fuzzy_matching = strategy.get("fuzzy_matching") or {}
        
        fuzzy_enabled = fuzzy_matching.get("enabled")
        if fuzzy_enabled is False:
            return False
            
        return (
            strategy.get("dedup_scope") == "entity_level"
            or "fuzzy_entity" in duplicate_types
            or fuzzy_enabled is True
        )

    def _build_planner_owned_decision(
        self,
        df: pd.DataFrame,
        dedup_input: DeduplicationAgentInput,
    ) -> ValidatedDedupDecision | None:
        planner_task = dedup_input.planner_task
        if planner_task is None or planner_task.skip:
            return None

        strategy = self._to_dict(planner_task.strategy) or {}
        primary_keys = self._dedupe_columns(
            strategy.get("primary_keys")
            or (strategy.get("key_based") or {}).get("keys")
            or planner_task.columns
        )
        ignored_columns = self._dedupe_columns(strategy.get("ignored_columns") or [])
        effective_keys = [column for column in primary_keys if column not in set(ignored_columns)]
        keep_rule = self._planner_keep_rule(strategy)
        mode = "exact_key" if effective_keys else "exact_full_row"

        semantic_seed_columns = self._dedupe_columns(
            effective_keys
            + list(strategy.get("identifier_columns") or [])
            + list((strategy.get("fuzzy_matching") or {}).get("match_columns") or [])
            + list((strategy.get("fuzzy_matching") or {}).get("blocking_columns") or [])
        )
        column_semantics = self._resolve_column_semantics(semantic_seed_columns, dedup_input)
        raw_planner_decision = DedupDecision(
            mode=mode,
            key_columns=effective_keys,
            column_semantics={
                column: descriptor.model_dump(mode="json")
                for column, descriptor in column_semantics.items()
            },
            ignore_columns=ignored_columns,
            fuzzy_plan=None,
            confidence=1.0,
            reasoning_summary="Planner provided the primary dedup strategy for execution.",
        )
        validated = self._validate_dedup_decision(raw_planner_decision, df, dedup_input)
        return validated.model_copy(
            update={
                "decision_source": "planner_fallback",
                "reasoning_summary": "Planner provided the primary dedup strategy for execution.",
                "keep_rule": keep_rule,
                "validation_notes": list(validated.validation_notes)
                + ["Planner strategy was used as the primary dedup execution input."],
            }
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
            "available_column_semantic_examples": [
                "phone-like identifier",
                "email-like identifier",
                "organization-like entity name",
                "person-like entity name",
                "address-like location",
                "identifier-like field",
                "generic text similarity",
            ],
            "available_fuzzy_strategies": [
                "token_blocking",
                "ngram_blocking",
                "word_shingle_blocking",
                "minhash_lsh",
            ],
            "available_block_key_transforms": [
                "normalized_prefix",
                "sorted_token_prefix",
                "domain",
                "area_code",
                "year",
                "exact_normalized",
            ],
            "pk_candidates": statistical_profile.get("pk_candidates", []),
            "near_unique_columns": statistical_profile.get("near_unique_columns", []),
            "high_null_columns": statistical_profile.get("high_null_columns", []),
            "planner_task": planner_task,
            "suggested_candidate_sets": self._build_suggested_candidate_sets(dedup_input),
            "suggested_fuzzy_columns": self._build_suggested_fuzzy_columns(dedup_input),
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
                column_semantics={},
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
        sanitized_llm_semantics = self._sanitize_llm_column_semantics(
            decision.column_semantics,
            df.columns,
            dedup_input,
        )
        validated_fuzzy_plan = self._validate_fuzzy_plan(
            decision.fuzzy_plan,
            sanitized_llm_semantics,
            df,
            dedup_input,
            ignore_columns=decision.ignore_columns,
        )
        requested = self._dedupe_columns(
            [column for column in decision.key_columns if column not in set(decision.ignore_columns)]
        )
        resolved_column_semantics = self._resolve_column_semantics(
            requested,
            dedup_input,
            llm_semantics=sanitized_llm_semantics,
        )
        missing = [column for column in requested if column not in df.columns]
        if missing:
            return self._fallback_decision(
                df,
                dedup_input,
                column_semantics=sanitized_llm_semantics,
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
                column_semantics=sanitized_llm_semantics,
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
                column_semantics=sanitized_llm_semantics,
                ignore_columns=list(decision.ignore_columns),
                fuzzy_plan=validated_fuzzy_plan,
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
                column_semantics=sanitized_llm_semantics,
                validation_notes=validation_notes + ["All candidate key columns were null in more than 80% of rows."],
                reasoning_summary=decision.reasoning_summary or "The LLM key set was too sparse to trust.",
            )

        if decision.mode == "exact_key":
            if self._is_name_only_key(filtered, dedup_input, column_semantics=resolved_column_semantics):
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
                    column_semantics=sanitized_llm_semantics,
                    validation_notes=validation_notes,
                    reasoning_summary=decision.reasoning_summary or "Name-only keys are not safe for automatic deduplication.",
                    unresolved_collisions=unresolved_collisions,
                )
            if len(filtered) == 1 and self._is_weak_single_key(filtered[0], dedup_input, column_semantics=resolved_column_semantics):
                unresolved_collisions.append(
                    {
                        "collision_type": "weak_phone_only"
                        if self._looks_like_phone_identifier(
                            filtered[0],
                            dedup_input,
                            column_semantics=resolved_column_semantics,
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
                    column_semantics=sanitized_llm_semantics,
                    validation_notes=validation_notes,
                    reasoning_summary=decision.reasoning_summary or "Weak single-field keys are not safe for automatic deduplication.",
                    unresolved_collisions=unresolved_collisions,
                )
            if decision.confidence is not None and decision.confidence < 0.6:
                validation_notes.append("LLM confidence was below 0.6; proceeding because the key set passed deterministic validation.")
            return ValidatedDedupDecision(
                mode="exact_key",
                key_columns=filtered,
                column_semantics=sanitized_llm_semantics,
                ignore_columns=list(decision.ignore_columns),
                fuzzy_plan=validated_fuzzy_plan,
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
            column_semantics=sanitized_llm_semantics,
            ignore_columns=list(decision.ignore_columns),
            fuzzy_plan=validated_fuzzy_plan,
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
        column_semantics: dict[str, ColumnSemanticDescriptor] | None,
        validation_notes: list[str],
        reasoning_summary: str,
        unresolved_collisions: list[dict[str, Any]] | None = None,
    ) -> ValidatedDedupDecision:
        unresolved_collisions = unresolved_collisions or []
        planner_task = dedup_input.planner_task
        if planner_task:
            strategy = self._to_dict(planner_task.strategy) or {}
            primary_keys = self._dedupe_columns(strategy.get("primary_keys") or [])
            planner_primary_semantics = self._resolve_column_semantics(primary_keys, dedup_input)
            if primary_keys and not self._is_name_only_key(primary_keys, dedup_input, column_semantics=planner_primary_semantics) and self._candidate_has_duplicates(df, primary_keys, dedup_input):
                return ValidatedDedupDecision(
                    mode="exact_key",
                    key_columns=primary_keys,
                    column_semantics=self._merge_column_semantics(column_semantics, planner_primary_semantics),
                    ignore_columns=[],
                    fuzzy_plan=self._build_default_fuzzy_plan(
                        df,
                        dedup_input,
                        column_semantics=self._merge_column_semantics(column_semantics, planner_primary_semantics),
                    ),
                    decision_source="planner_fallback",
                    confidence=None,
                    reasoning_summary=reasoning_summary,
                    validation_notes=validation_notes + ["Used planner strategy.primary_keys as fallback."],
                    unresolved_collisions=unresolved_collisions,
                )
            planner_columns = self._dedupe_columns(planner_task.columns)
            planner_column_semantics = self._resolve_column_semantics(planner_columns, dedup_input)
            if planner_columns and not self._is_name_only_key(planner_columns, dedup_input, column_semantics=planner_column_semantics) and self._candidate_has_duplicates(df, planner_columns, dedup_input):
                return ValidatedDedupDecision(
                    mode="exact_key",
                    key_columns=planner_columns,
                    column_semantics=self._merge_column_semantics(column_semantics, planner_column_semantics),
                    ignore_columns=[],
                    fuzzy_plan=self._build_default_fuzzy_plan(
                        df,
                        dedup_input,
                        column_semantics=self._merge_column_semantics(column_semantics, planner_column_semantics),
                    ),
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
                candidate_semantics = self._resolve_column_semantics(candidate, dedup_input)
                if self._candidate_has_duplicates(df, candidate, dedup_input):
                    return ValidatedDedupDecision(
                        mode="exact_key",
                        key_columns=candidate,
                        column_semantics=self._merge_column_semantics(column_semantics, candidate_semantics),
                        ignore_columns=[],
                        fuzzy_plan=self._build_default_fuzzy_plan(
                            df,
                            dedup_input,
                            column_semantics=self._merge_column_semantics(column_semantics, candidate_semantics),
                        ),
                        decision_source="profile_fallback",
                        confidence=None,
                        reasoning_summary=reasoning_summary,
                        validation_notes=validation_notes + [f"Used statistical profile candidate {candidate} as fallback."],
                        unresolved_collisions=unresolved_collisions,
                    )

        return ValidatedDedupDecision(
            mode="exact_full_row",
            key_columns=[],
            column_semantics=dict(column_semantics or {}),
            ignore_columns=[],
            fuzzy_plan=self._build_default_fuzzy_plan(
                df,
                dedup_input,
                column_semantics=dict(column_semantics or {}),
            ),
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

        # ── TRACE: STEP 1 – Full-row dedup ────────────────────────────────────
        print("[DEDUP_TRACE] ── STEP 1: full-row dedup ───────────────────────────")
        print(f"[DEDUP_TRACE]   before={before_row_count}, removed={full_row_duplicate_count}, after={len(deduped_df)}")
        if "ProviderNumber" in deduped_df.columns:
            _pn = deduped_df["ProviderNumber"].astype(str)
            print(f"[DEDUP_TRACE]   10018 rows after step 1: {int((_pn == '10018').sum())}")
        # ──────────────────────────────────────────────────────────────────────

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
                    column_semantics=validated_decision.column_semantics,
                    semantic_profile=dedup_input.semantic_profile,
                    statistical_profile=dedup_input.statistical_profile,
                    keep_rule=validated_decision.keep_rule,
                    notes=[],
                    unresolved_collisions=unresolved_collisions,
                ),
            )
            key_duplicate_count = key_execution.key_duplicate_count

            # ── TRACE: STEP 2 – Exact-key dedup ───────────────────────────────
            print("[DEDUP_TRACE] ── STEP 2: exact-key dedup ──────────────────────")
            print(f"[DEDUP_TRACE]   key_cols={validated_decision.key_columns}")
            print(f"[DEDUP_TRACE]   key_dupes_removed={key_duplicate_count}, after={len(key_execution.deduped_df)}")
            if "ProviderNumber" in key_execution.deduped_df.columns:
                _pn2 = key_execution.deduped_df["ProviderNumber"].astype(str)
                print(f"[DEDUP_TRACE]   10018 rows after step 2: {int((_pn2 == '10018').sum())}")
                # Show any provider that now has 0 rows (disappeared entirely)
                if "ProviderNumber" in deduped_df.columns:
                    _before_provs = set(deduped_df["ProviderNumber"].dropna().unique())
                    _after_provs = set(key_execution.deduped_df["ProviderNumber"].dropna().unique())
                    _lost = _before_provs - _after_provs
                    if _lost:
                        print(f"[DEDUP_TRACE]   WARN: providers entirely removed by key dedup: {sorted(_lost)}")
            # ──────────────────────────────────────────────────────────────────

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

    def _coerce_existing_result(self, state: GlobalState) -> DeduplicationResult | None:
        worker_outputs = state.get("worker_outputs") or {}
        existing = worker_outputs.get(self.name) if isinstance(worker_outputs, dict) else None
        if not existing:
            return None
        return DeduplicationResult.model_validate(existing)

    def _rebuild_decision_from_state(
        self,
        state: GlobalState,
        context_hash: str,
    ) -> ValidatedDedupDecision | None:
        existing_result = self._coerce_existing_result(state)
        if not existing_result:
            return None
        trace = existing_result.decision_trace
        if trace is None or trace.context_hash != context_hash:
            return None

        mode = "exact_key" if existing_result.key_columns else "exact_full_row"
        return ValidatedDedupDecision(
            mode=mode,
            key_columns=list(existing_result.key_columns),
            column_semantics={
                column: ColumnSemanticDescriptor.model_validate(descriptor)
                for column, descriptor in trace.column_semantics.items()
            },
            ignore_columns=list(trace.ignore_columns),
            fuzzy_plan=FuzzyExecutionPlan.model_validate(trace.fuzzy_plan) if trace.fuzzy_plan else None,
            decision_source=trace.decision_source,
            confidence=trace.confidence,
            reasoning_summary=trace.reasoning_summary,
            keep_rule=existing_result.keep_strategy if existing_result.keep_strategy in {"keep_most_complete", "keep_first", "keep_last"} else "keep_most_complete",
            validation_notes=list(trace.validation_notes),
            unresolved_collisions=[],
        )

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
            explicit_semantics=self._resolve_column_semantics(columns, dedup_input),
            semantic_profile=dedup_input.semantic_profile,
        )

    def _run_fuzzy_blocking(
        self,
        df: pd.DataFrame,
        validated_decision: ValidatedDedupDecision,
        dedup_input: DeduplicationAgentInput,
    ) -> FuzzyCandidateSet:
        if not validated_decision.fuzzy_plan or not validated_decision.fuzzy_plan.enabled:
            print(f"FUZZY_DEBUG: Plan is disabled or None! Plan: {validated_decision.fuzzy_plan}")
            return FuzzyCandidateSet(notes=["Fuzzy planning was disabled for this dataset."])
        print(f"FUZZY_DEBUG: Plan ENABLED, specs = {len(validated_decision.fuzzy_plan.blocking_specs)}")
        return run_fuzzy_blocking(
            df,
            plan=validated_decision.fuzzy_plan,
            key_columns=validated_decision.key_columns,
            config=FuzzyBlockingConfig(),
        )

    @staticmethod
    def _count_duplicate_rows(df: pd.DataFrame, key_columns: list[str]) -> int:
        if not key_columns or any(column not in df.columns for column in key_columns):
            return 0
        return int(df.duplicated(subset=key_columns, keep=False).sum())

    def _count_name_only_collision_rows(self, df: pd.DataFrame, key_columns: list[str]) -> int:
        return self._count_duplicate_rows(df, key_columns)

    def _resolve_column_semantics(
        self,
        columns: list[str],
        dedup_input: DeduplicationAgentInput,
        *,
        llm_semantics: dict[str, ColumnSemanticDescriptor] | None = None,
    ) -> dict[str, ColumnSemanticDescriptor]:
        resolved: dict[str, ColumnSemanticDescriptor] = {}
        for column in columns:
            descriptor = infer_column_semantics(
                column,
                explicit_semantics=llm_semantics,
                semantic_profile=dedup_input.semantic_profile,
            )
            if descriptor is not None:
                resolved[column] = descriptor
        return resolved

    @staticmethod
    def _merge_column_semantics(
        primary: dict[str, ColumnSemanticDescriptor] | None,
        secondary: dict[str, ColumnSemanticDescriptor] | None,
    ) -> dict[str, ColumnSemanticDescriptor]:
        merged = dict(primary or {})
        merged.update(secondary or {})
        return merged

    def _sanitize_llm_column_semantics(
        self,
        raw_semantics: dict[str, dict[str, Any]] | None,
        available_columns: Any,
        dedup_input: DeduplicationAgentInput,
    ) -> dict[str, ColumnSemanticDescriptor]:
        sanitized: dict[str, ColumnSemanticDescriptor] = {}
        if not raw_semantics:
            return sanitized
        available = set(available_columns)
        for column, payload in raw_semantics.items():
            if column not in available:
                continue
            try:
                descriptor = ColumnSemanticDescriptor.model_validate(payload)
            except Exception:
                continue
            resolved = infer_column_semantics(
                column,
                explicit_semantics={column: descriptor},
                semantic_profile=dedup_input.semantic_profile,
            )
            if resolved is not None:
                sanitized[column] = resolved
        return sanitized

    def _is_name_only_key(
        self,
        key_columns: list[str],
        dedup_input: DeduplicationAgentInput,
        *,
        column_semantics: dict[str, ColumnSemanticDescriptor] | None = None,
    ) -> bool:
        if not key_columns:
            return False
        if not all(self._is_name_like_column(column, dedup_input, column_semantics=column_semantics) for column in key_columns):
            return False
        return not any(
            self._is_hard_identifier_column(column, dedup_input, column_semantics=column_semantics)
            for column in key_columns
        )

    def _is_name_like_column(
        self,
        column_name: str,
        dedup_input: DeduplicationAgentInput,
        *,
        column_semantics: dict[str, ColumnSemanticDescriptor] | None = None,
    ) -> bool:
        descriptor = infer_column_semantics(
            column_name,
            explicit_semantics=column_semantics,
            semantic_profile=dedup_input.semantic_profile,
        )
        return descriptor_is_name_like(descriptor)

    def _is_hard_identifier_column(
        self,
        column_name: str,
        dedup_input: DeduplicationAgentInput,
        *,
        column_semantics: dict[str, ColumnSemanticDescriptor] | None = None,
    ) -> bool:
        descriptor = infer_column_semantics(
            column_name,
            explicit_semantics=column_semantics,
            semantic_profile=dedup_input.semantic_profile,
        )
        if (
            dedup_input.planner_task 
            and dedup_input.planner_task.strategy 
            and column_name in (dedup_input.planner_task.strategy.identifier_columns or [])
        ):
            return True

        if descriptor_is_hard_identifier(descriptor):
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
                
        return False

    def _looks_like_phone_identifier(
        self,
        column_name: str,
        dedup_input: DeduplicationAgentInput,
        *,
        column_semantics: dict[str, ColumnSemanticDescriptor] | None = None,
    ) -> bool:
        descriptor = infer_column_semantics(
            column_name,
            explicit_semantics=column_semantics,
            semantic_profile=dedup_input.semantic_profile,
        )
        return "phone" in " ".join(
            [
                descriptor.normalization_intent,
                descriptor.identifier_intent,
                descriptor.comparison_intent,
                descriptor.semantic_label,
            ]
        ).casefold() if descriptor else False

    def _is_weak_single_key(
        self,
        column_name: str,
        dedup_input: DeduplicationAgentInput,
        *,
        column_semantics: dict[str, ColumnSemanticDescriptor] | None = None,
    ) -> bool:
        return not self._is_hard_identifier_column(column_name, dedup_input, column_semantics=column_semantics)

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
            explicit_semantics=self._resolve_column_semantics(key_columns, dedup_input),
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

    def _build_suggested_fuzzy_columns(self, dedup_input: DeduplicationAgentInput) -> list[str]:
        available_columns = list((dedup_input.dataset_schema or {}).keys())
        candidates: list[str] = []
        for column in available_columns:
            descriptor = infer_column_semantics(column, semantic_profile=dedup_input.semantic_profile)
            if resolve_name_family(descriptor) in {"organization_name", "person_name", "address"}:
                candidates.append(column)
        return self._dedupe_columns(candidates)[:10]

    def _validate_fuzzy_plan(
        self,
        raw_plan: dict[str, Any] | None,
        llm_semantics: dict[str, ColumnSemanticDescriptor],
        df: pd.DataFrame,
        dedup_input: DeduplicationAgentInput,
        *,
        ignore_columns: list[str],
    ) -> FuzzyExecutionPlan | None:
        if not dedup_input.fuzzy_enabled:
            return None

        candidate_plan: FuzzyExecutionPlan | None = None
        if raw_plan:
            try:
                candidate_plan = FuzzyExecutionPlan.model_validate(raw_plan)
            except Exception:
                candidate_plan = None

        if candidate_plan is None or not candidate_plan.enabled:
            return self._build_default_fuzzy_plan(
                df,
                dedup_input,
                column_semantics=llm_semantics,
                ignore_columns=ignore_columns,
            )

        ignored = set(ignore_columns)
        valid_specs: list[BlockingSpec] = []
        for spec in candidate_plan.blocking_specs:
            targets = self._dedupe_columns(
                [column for column in spec.target_columns if column in df.columns and column not in ignored]
            )
            if not targets:
                continue

            block_keys = []
            for block_key in spec.block_keys:
                columns = self._dedupe_columns(
                    [column for column in block_key.columns if column in df.columns and column not in ignored]
                )
                if columns:
                    block_keys.append(block_key.model_copy(update={"columns": columns}))

            sub_block_columns = self._dedupe_columns(
                [
                    column
                    for column in spec.sub_block_columns
                    if column in df.columns and column not in ignored and column not in targets
                ]
            )

            valid_specs.append(
                BlockingSpec(
                    spec_id=spec.spec_id or self._derive_blocking_spec_id(spec, targets),
                    target_columns=targets,
                    semantic_label=spec.semantic_label or spec.comparison_intent or spec.blocking_intent,
                    comparison_intent=spec.comparison_intent,
                    blocking_intent=spec.blocking_intent,
                    strategy=spec.strategy,
                    block_keys=block_keys,
                    sub_block_columns=sub_block_columns,
                    similarity_metric=spec.similarity_metric,
                    similarity_threshold=self._clamp_similarity_threshold(
                        spec.similarity_threshold,
                        comparison_intent=spec.comparison_intent,
                    ),
                    max_bucket_size=max(50, spec.max_bucket_size),
                    oversized_bucket_strategy=spec.oversized_bucket_strategy,
                )
            )

        if not valid_specs:
            return self._build_default_fuzzy_plan(
                df,
                dedup_input,
                column_semantics=llm_semantics,
                ignore_columns=ignore_columns,
            )

        evidence_specs: list[EvidenceSpec] = []
        valid_spec_ids = {spec.spec_id for spec in valid_specs}
        for spec in candidate_plan.evidence_specs:
            support_columns = self._dedupe_columns(
                [column for column in spec.support_columns if column in df.columns and column not in ignored]
            )
            reject_columns = self._dedupe_columns(
                [column for column in spec.reject_columns if column in df.columns and column not in ignored]
            )
            target_blocking_specs = [
                spec_id for spec_id in spec.target_blocking_specs if spec_id in valid_spec_ids
            ]
            evidence_specs.append(
                EvidenceSpec(
                    target_blocking_specs=target_blocking_specs,
                    support_columns=support_columns,
                    reject_columns=reject_columns,
                    minimum_support_matches=max(0, spec.minimum_support_matches),
                    hard_reject_on_conflict=spec.hard_reject_on_conflict,
                )
            )

        return FuzzyExecutionPlan(
            enabled=True,
            entity_scope=candidate_plan.entity_scope,
            blocking_specs=valid_specs,
            evidence_specs=evidence_specs,
            candidate_resolution_policy=candidate_plan.candidate_resolution_policy,
            notes=list(candidate_plan.notes),
        )

    def _build_default_fuzzy_plan(
        self,
        df: pd.DataFrame,
        dedup_input: DeduplicationAgentInput,
        *,
        column_semantics: dict[str, ColumnSemanticDescriptor] | None,
        ignore_columns: list[str] | None = None,
    ) -> FuzzyExecutionPlan | None:
        if not dedup_input.fuzzy_enabled:
            return None

        ignored = set(ignore_columns or [])
        target_specs: list[BlockingSpec] = []
        for column in df.columns:
            if column in ignored:
                continue
            descriptor = infer_column_semantics(
                column,
                explicit_semantics=column_semantics,
                semantic_profile=dedup_input.semantic_profile,
            )
            family = resolve_name_family(descriptor)
            if family not in {"organization_name", "person_name", "address"}:
                continue
            strategy = "word_shingle_blocking" if family == "address" else "ngram_blocking"
            sub_block_columns = self._pick_fuzzy_support_columns(
                df,
                dedup_input,
                excluded_columns={column, *ignored},
            )
            target_specs.append(
                BlockingSpec(
                    spec_id=f"{family}:{column}".replace(" ", "_"),
                    target_columns=[column],
                    semantic_label=descriptor.semantic_label if descriptor else family,
                    comparison_intent=descriptor.comparison_intent if descriptor else family,
                    blocking_intent=descriptor.blocking_intent if descriptor else "generic fuzzy blocking",
                    strategy=strategy,
                    block_keys=[
                        self._default_block_key_spec(family)
                    ],
                    sub_block_columns=sub_block_columns[:2],
                    similarity_metric="jaccard",
                    similarity_threshold=self._default_fuzzy_threshold(family),
                    max_bucket_size=FuzzyBlockingConfig().max_bucket_size,
                    oversized_bucket_strategy="sub_block",
                )
            )

        if not target_specs:
            return FuzzyExecutionPlan(
                enabled=False,
                notes=["No address/name/company columns were suitable for fuzzy planning."],
            )

        support_columns = self._pick_fuzzy_support_columns(df, dedup_input, excluded_columns=ignored)
        reject_columns = [
            column
            for column in support_columns
            if self._is_hard_identifier_column(column, dedup_input)
        ]
        evidence_specs = [
            EvidenceSpec(
                target_blocking_specs=[
                    spec.spec_id for spec in target_specs if self._resolve_internal_execution_family(spec.comparison_intent) == "organization_name"
                ],
                support_columns=support_columns,
                reject_columns=reject_columns,
                minimum_support_matches=1,
                hard_reject_on_conflict=True,
            ),
            EvidenceSpec(
                target_blocking_specs=[
                    spec.spec_id for spec in target_specs if self._resolve_internal_execution_family(spec.comparison_intent) == "person_name"
                ],
                support_columns=support_columns,
                reject_columns=reject_columns,
                minimum_support_matches=1,
                hard_reject_on_conflict=True,
            ),
            EvidenceSpec(
                target_blocking_specs=[
                    spec.spec_id for spec in target_specs if self._resolve_internal_execution_family(spec.comparison_intent) == "address"
                ],
                support_columns=support_columns,
                reject_columns=reject_columns,
                minimum_support_matches=1,
                hard_reject_on_conflict=False,
            ),
            EvidenceSpec(
                target_blocking_specs=[
                    spec.spec_id for spec in target_specs if self._resolve_internal_execution_family(spec.comparison_intent) not in {"organization_name", "person_name", "address"}
                ],
                support_columns=support_columns,
                reject_columns=reject_columns,
                minimum_support_matches=1,
                hard_reject_on_conflict=True,
            ),
        ]
        return FuzzyExecutionPlan(
            enabled=True,
            entity_scope="mixed",
            blocking_specs=target_specs,
            evidence_specs=evidence_specs,
            candidate_resolution_policy="preview_only",
            notes=["Used semantic/profile-driven fuzzy fallback planning because no valid LLM fuzzy plan was available."],
        )

    @staticmethod
    def _default_block_key_spec(family: str) -> BlockKeySpec:
        transform = "sorted_token_prefix" if family == "address" else "normalized_prefix"
        return BlockKeySpec(columns=[], transform=transform, required=False)

    @staticmethod
    def _default_fuzzy_threshold(family: str | None) -> float:
        if family == "address":
            return FuzzyBlockingConfig().address_threshold
        if family == "person_name":
            return FuzzyBlockingConfig().person_threshold
        return FuzzyBlockingConfig().company_threshold

    def _pick_fuzzy_support_columns(
        self,
        df: pd.DataFrame,
        dedup_input: DeduplicationAgentInput,
        *,
        excluded_columns: set[str],
    ) -> list[str]:
        scored: list[tuple[float, str]] = []
        for column in df.columns:
            if column in excluded_columns:
                continue
            if self._looks_like_technical_id(column, dedup_input):
                continue
            score = 0.0
            if self._is_hard_identifier_column(column, dedup_input):
                score += 5.0
            descriptor = infer_column_semantics(column, semantic_profile=dedup_input.semantic_profile)
            if descriptor_is_hard_identifier(descriptor):
                score += 3.0
            stat_column = self._get_statistical_column(dedup_input, column)
            if stat_column:
                score += max(0.0, 1.0 - float(stat_column.null_rate))
                score += min(float(stat_column.unique_ratio), 1.0)
            if score > 0:
                scored.append((score, column))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [column for _, column in scored[:5]]

    def _clamp_similarity_threshold(self, value: float, *, comparison_intent: str) -> float:
        if not 0.0 <= value <= 1.0:
            return self._default_fuzzy_threshold(self._resolve_internal_execution_family(comparison_intent))
        return value

    @staticmethod
    def _resolve_internal_execution_family(comparison_intent: str | None) -> str:
        family = (comparison_intent or "").strip().casefold()
        aliases = {
            "organization_name": "organization_name",
            "organization": "organization_name",
            "company_name": "organization_name",
            "company": "organization_name",
            "organization-like entity name": "organization_name",
            "organization entity name": "organization_name",
            "facility-like entity name": "organization_name",
            "person_name": "person_name",
            "person": "person_name",
            "person-like entity name": "person_name",
            "person entity name": "person_name",
            "address": "address",
            "location": "address",
            "address-like location": "address",
            "address text similarity": "address",
            "location-like address": "address",
            "generic_text": "generic_text",
            "text": "generic_text",
        }
        return aliases.get(family, "generic_text")

    def _derive_blocking_spec_id(self, spec: BlockingSpec, targets: list[str]) -> str:
        semantic_label = (spec.semantic_label or spec.comparison_intent or "fuzzy").replace(" ", "_")
        target_stub = "_".join(targets[:2]).replace(" ", "_")
        return f"{semantic_label}:{target_stub}"

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
    def _planner_keep_rule(strategy: dict[str, Any]) -> str:
        explicit = strategy.get("keep_rule")
        if explicit in {"keep_most_complete", "keep_first", "keep_last"}:
            return explicit

        key_based = strategy.get("key_based") or {}
        survivor_policy = key_based.get("survivor_policy") or {}
        fallback = survivor_policy.get("fallback")
        if fallback == "last":
            return "keep_last"
        if fallback == "first":
            return "keep_first"
        return "keep_most_complete"

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
