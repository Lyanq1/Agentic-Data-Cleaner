"""Planner Agent — copy and customize to create a new agent."""
import json
import logging
import re
from pathlib import Path
from typing import Any
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage

from app.agents.base import BaseAgent
from app.agents.registry import AgentRegistry
from datetime import datetime
from app.graphs.states.global_state import GlobalState

from app.graphs.states.planning import (
    ExecutionPlan,
    TaskDetail,
    TaskDetailWrapper,
    PlanMetadata,
    GlobalConstraints,
    PlanReview,
    ReviewField,
    ReviewSection,
)

logger = logging.getLogger(__name__)


@AgentRegistry.auto_register
class PlannerAgent(BaseAgent):
    """Generates the data cleaning DAG and execution plan based on profiles and user inputs."""

    name = "planner"
    description = "Generates a structured execution plan for deduplication, null handling, and type casting."
    tools = []  # pure LLM reasoning

    _EXECUTION_ORDER = ["deduplication", "type_casting", "null_handling"]

    async def run(self, state: GlobalState) -> dict[str, Any]:
        """Invoke the LLM to generate the ExecutionPlan.

        Args:
            state: Current GlobalState dict.

        Returns:
            State updates with the execution plan and task list.
            - execution_plan: ExecutionPlan Pydantic model.
            - task_list: List[str] containing mapped active task ids.
        """
        data_profile = state.get("statistical_profile")
        semantic_profile = state.get("semantic_profile")
        validation_result = state.get("input_validation_result")
        user_prompt = state.get("user_prompt", "")
        prior_messages = state.get("messages", [])

        # Output Validation Feedback for Replanning
        replan_reason = state.get("replan_reason")
        last_validation_error = state.get("last_validation_error")
        validation_results = state.get("validation_results", [])
        latest_replan_hints = {}
        if validation_results:
            latest_result = validation_results[-1]
            if hasattr(latest_result, "replan_hints"):
                latest_replan_hints = latest_result.replan_hints
            elif isinstance(latest_result, dict):
                latest_replan_hints = latest_result.get("replan_hints", {})

        # Format profiles safely (handling dict or Pydantic models)
        def to_dict(obj: Any) -> Any:
            if not obj:
                return None
            if hasattr(obj, "model_dump"):
                return obj.model_dump()
            elif hasattr(obj, "dict"):
                return obj.dict()
            return obj

        data_profile_dict = to_dict(data_profile)
        semantic_profile_dict = to_dict(semantic_profile)
        validation_dict = to_dict(validation_result)

        if semantic_profile_dict and "thinking" in semantic_profile_dict:
            # Remove thinking field to reduce token usage and avoid confusing the LLM parser
            del semantic_profile_dict["thinking"]

        pipeline_mode = state.get("pipeline_mode", "interactive")
        if pipeline_mode == "benchmark":
            user_instruction_block = "N/A — no user requirement; goal is the cleanest possible version of this dataset."
        else:
            user_instruction_block = user_prompt

        human_content = (
            f"## User Instruction\n{user_instruction_block}\n\n"
        )
        if validation_dict:
            human_content += f"## Input Validation Decision\n```json\n{json.dumps(validation_dict, indent=2, default=str)}\n```\n\n"
        if data_profile_dict:
            human_content += f"## Dataset Statistical Profile\n```json\n{json.dumps(data_profile_dict, indent=2, default=str)}\n```\n\n"
        if semantic_profile_dict:
            human_content += f"## Dataset Semantic Profile\n```json\n{json.dumps(semantic_profile_dict, indent=2, default=str)}\n```\n"

        if replan_reason or last_validation_error:
            human_content += f"## REPLAN REQUIRED\nThe previous plan failed validation. You must adjust your plan or strategy based on this feedback to avoid failing again.\n"
            if replan_reason:
                human_content += f"- **Replan Reason**: {replan_reason}\n"
            if last_validation_error:
                human_content += f"- **Validation Error**: {last_validation_error}\n"
            if latest_replan_hints:
                human_content += f"- **Hints**: {json.dumps(latest_replan_hints, indent=2, default=str)}\n"
            human_content += "\n"

        # Load the planner skill file dynamically
        skill_path = Path.cwd() / ".agents" / "skills" / "data-cleaning-planner" / "SKILL.md"
        if skill_path.exists():
            with open(skill_path, "r", encoding="utf-8") as f:
                content = f.read()
                # Strip YAML frontmatter if present
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        planner_system_prompt = parts[2].strip()
                    else:
                        planner_system_prompt = content
                else:
                    planner_system_prompt = content
        else:
            logger.warning(f"PlannerAgent: Skill file not found at {skill_path}. Falling back to default prompt.")
            from app.agents.planner.prompts import PLANNER_SYSTEM_PROMPT as planner_system_prompt

        messages = [
            SystemMessage(content=planner_system_prompt),
            HumanMessage(content=human_content),
        ]

        # Append any prior conversation history so the LLM remembers previous answers
        for msg in prior_messages:
            if isinstance(msg, (HumanMessage, AIMessage)):
                messages.append(msg)

        # Force JSON output mode
        messages.append(SystemMessage(content="CRITICAL: You must output ONLY a valid JSON object matching the requested schema. Do NOT wrap the response in markdown code blocks like ```json ... ```, and do NOT add any trailing characters or conversational text."))

        logger.info("PlannerAgent: invoking LLM for structured execution planning...")
        
        try:
            json_llm = self.llm.bind(response_format={"type": "json_object"})
            raw_response = await json_llm.ainvoke(messages)
            content = raw_response.content
            
            # Clean up the output string in case the model ignores the response_format and uses markdown
            content_clean = content.strip()
            if content_clean.startswith("```json"):
                content_clean = content_clean[7:]
            elif content_clean.startswith("```"):
                content_clean = content_clean[3:]
            if content_clean.endswith("```"):
                content_clean = content_clean[:-3]
            content_clean = content_clean.strip()
            
            # Extract only the JSON object boundaries
            start = content_clean.find("{")
            end = content_clean.rfind("}")
            if start != -1 and end != -1:
                content_clean = content_clean[start:end+1]
                
            response = ExecutionPlan.model_validate_json(content_clean)
        except Exception as e:
            logger.error(f"PlannerAgent failed to parse LLM JSON output: {e}")
            # Fallback to a safe execution plan where we skip all and log the error
            response = ExecutionPlan(
                metadata=PlanMetadata(
                    plan_id="fallback",
                    plan_version=1,
                    created_at=datetime.now().isoformat()
                ),
                global_constraints=GlobalConstraints(
                    max_retries_per_task=3,
                    preserve_columns=[]
                ),
                task_list=[
                  TaskDetailWrapper(
                      work_order=TaskDetail(
                          task_id="deduplication",
                          agent="dedup_agent",
                          skip=True,
                          skip_reason=f"Failed to generate plan due to error: {e}",
                          columns=[],
                          strategy={}
                      )
                  ),
                  TaskDetailWrapper(
                      work_order=TaskDetail(
                          task_id="type_casting",
                          agent="typecast_agent",
                          skip=True,
                          skip_reason=f"Failed to generate plan due to error: {e}",
                          columns=[],
                          strategy={}
                      )
                  ),
                  TaskDetailWrapper(
                      work_order=TaskDetail(
                          task_id="null_handling",
                          agent="null_agent",
                          skip=True,
                          skip_reason=f"Failed to generate plan due to error: {e}",
                          columns=[],
                          strategy={}
                      )
                  )
                ],
                plan_summary=f"Fallback execution plan created because LLM plan parsing failed: {e}."
            )

        response = response.model_copy(
            update={
                "review": self._build_plan_review(
                    response,
                    state.get("semantic_profile"),
                    validation_result,
                )
            }
        )

        logger.info("PlannerAgent successfully parsed execution plan.")

        # Enforce execution sequence: deduplication -> type_casting -> null_handling
        active_tasks_set = {
            task.work_order.task_id
            for task in response.task_list
            if not task.work_order.skip
        }
        active_task_names = []
        for task_id in self._EXECUTION_ORDER:
            if task_id in active_tasks_set:
                active_task_names.append(task_id)

        logger.info(f"PlannerAgent active task list: {active_task_names}")

        json_data = response.model_dump()
        final_message = json.dumps(json_data, ensure_ascii=False, indent=2)

        # Update state with the plan and the mapped task_list
        updates: dict[str, Any] = {
            "messages": [AIMessage(content=final_message, name=self.name)],
            "execution_plan": response,
            "task_list": active_task_names,
            "current_task_idx": 0,
            "retry_count": 0,
            "hitl_status": "pending" if active_task_names else None,
            "hitl_checkpoint": 0 if active_task_names else None,
        }

        return updates

    def _build_plan_review(
        self,
        plan: ExecutionPlan,
        semantic_profile: Any | None = None,
        validation_result: Any | None = None,
    ) -> PlanReview:
        sections: list[ReviewSection] = []
        warnings: list[str] = []

        for wrapper in plan.task_list:
            task = wrapper.work_order
            if task.task_id == "deduplication":
                sections.append(self._build_dedup_review_section(task))
                if task.rationale:
                    warnings.append(f"{task.task_id}: {task.rationale}")
                if task.skip_reason:
                    warnings.append(f"{task.task_id}: {task.skip_reason}")
                break

        null_section, null_warnings = self._build_null_strategy_review_section(
            plan, semantic_profile, validation_result
        )
        if null_section is not None:
            sections.append(null_section)
            warnings.extend(null_warnings)

        if not sections:
            warnings.append("No deduplication task is active in the current execution plan.")

        return PlanReview(sections=sections, warnings=warnings[:8])

    def _build_null_strategy_review_section(
        self,
        plan: ExecutionPlan,
        semantic_profile: Any | None,
        validation_result: Any | None,
    ) -> tuple[ReviewSection | None, list[str]]:
        task = next(
            (
                wrapper.work_order
                for wrapper in plan.task_list
                if wrapper.work_order.task_id == "null_handling" and not wrapper.work_order.skip
            ),
            None,
        )
        if task is None:
            return None, []

        strategy = self._strategy_dict(task)
        per_column = strategy.get("per_column") or {}
        semantic_columns = self._semantic_columns_dict(semantic_profile)
        validator_options = self._input_validator_null_options(validation_result)
        fields: list[ReviewField] = []
        warnings: list[str] = []

        for column, config in per_column.items():
            if not isinstance(config, dict):
                continue
            current = str(config.get("strategy") or "leave_as_is")
            detail = semantic_columns.get(column)
            if detail is None:
                continue
            semantic_type = str(self._detail_value(detail, "semantic_data_type", "Nominal"))
            raw_options = validator_options.get(column)
            option_source = "Input Validator"
            if not raw_options:
                raw_options = self._detail_value(detail, "fill_strategies", []) or []
                option_source = "semantic profile"
            compatible = [self._normalize_null_strategy(str(item)) for item in raw_options]
            supported = {
                "fill_mean", "fill_median", "fill_mode", "fill_value",
                "drop_row", "leave_as_is",
            }
            compatible = list(
                dict.fromkeys(option for option in compatible if option in supported)
            )
            final_dtype = self._planned_final_dtype(plan, task, column)
            compatible = [
                option
                for option in compatible
                if self._strategy_supported_by_final_dtype(option, final_dtype)
            ]
            fill_value = config.get("fill_value")
            expected_pattern = self._detail_value(detail, "expected_str_pattern", None)
            potential_dmv = list(self._detail_value(detail, "potential_dmv", []) or [])
            pattern_mismatch = False
            if current == "fill_value" and fill_value is not None and expected_pattern:
                try:
                    pattern_mismatch = re.match(str(expected_pattern), str(fill_value).strip()) is None
                except re.error:
                    pattern_mismatch = False
            dmv_mismatch = current == "fill_value" and fill_value in potential_dmv
            strategy_conflict = current not in compatible
            if not strategy_conflict and not pattern_mismatch and not dmv_mismatch:
                continue

            # Only a custom constant can be explicitly retained despite semantic
            # incompatibility. Other invalid strategies must be replaced by one of
            # the options already validated upstream.
            can_keep_current = current == "fill_value"
            options = (
                [current, *[option for option in compatible if option != current]]
                if can_keep_current
                else compatible
            )
            if not options:
                # Never let an unsupported planner strategy bypass HITL merely
                # because upstream did not provide alternatives.
                options = ["leave_as_is"]
            warning_parts: list[str] = []
            if strategy_conflict:
                warning_parts.append(
                    f"planner strategy '{current}' is not listed as compatible with semantic "
                    f"type '{semantic_type}' and planned final dtype '{final_dtype}'"
                )
            if pattern_mismatch:
                warning_parts.append(
                    f"fill_value '{fill_value}' does not match expected pattern "
                    f"'{expected_pattern}'"
                )
            if dmv_mismatch:
                warning_parts.append(
                    f"fill_value '{fill_value}' is classified as a disguised missing value"
                )
            warning = f"{column}: " + "; ".join(warning_parts) + "."
            warnings.append(warning)
            fields.append(
                ReviewField(
                    field_key=f"strategy.{column}",
                    label=f"Null strategy for {column}",
                    value=current if can_keep_current else options[0],
                    editable=True,
                    input_type="select",
                    options=options,
                    help_text=(
                        f"{warning} Options come from the {option_source}. "
                        + (
                            f"You may keep the explicit default value strategy '{current}' "
                            "or select a recommended alternative."
                            if can_keep_current
                            else "The incompatible strategy cannot be retained; select one "
                            "of the validated alternatives."
                        )
                    ),
                    metadata={
                        "expected_str_pattern": expected_pattern,
                        "potential_dmv": potential_dmv,
                        "pattern_mismatch": pattern_mismatch,
                        "dmv_mismatch": dmv_mismatch,
                    },
                )
            )

        if not fields:
            return None, []
        return ReviewSection(
            task_id="null_handling",
            title="Null strategy semantic conflicts",
            fields=fields,
        ), warnings

    @staticmethod
    def _normalize_null_strategy(strategy: str) -> str:
        strategy = strategy.removeprefix("(Recommended)").strip()
        return {
            "keep_null": "leave_as_is",
            "fill_constant": "fill_value",
        }.get(strategy, strategy)

    @classmethod
    def _input_validator_null_options(
        cls, validation_result: Any | None
    ) -> dict[str, list[str]]:
        if validation_result is None:
            return {}
        result = (
            validation_result
            if isinstance(validation_result, dict)
            else validation_result.model_dump()
        )
        clarifications = result.get("clarifications") or {}
        null_questions = clarifications.get("null") or {}
        options_by_column: dict[str, list[str]] = {}
        prefix = "Q2_strategy_column_"
        for key, question in null_questions.items():
            if not key.startswith(prefix) or not question:
                continue
            question_dict = question if isinstance(question, dict) else question.model_dump()
            options_by_column[key[len(prefix):]] = list(question_dict.get("options") or [])
        return options_by_column

    @classmethod
    def _planned_final_dtype(
        cls, plan: ExecutionPlan, null_task: TaskDetail, column: str
    ) -> str:
        type_task = next(
            (
                wrapper.work_order
                for wrapper in plan.task_list
                if wrapper.work_order.task_id == "type_casting"
                and not wrapper.work_order.skip
            ),
            None,
        )
        if type_task is not None:
            type_strategy = cls._strategy_dict(type_task)
            type_config = (type_strategy.get("per_column") or {}).get(column) or {}
            expected_type = type_config.get("expected_type")
            if expected_type:
                return str(expected_type).lower()

        if null_task.inputs and column in null_task.inputs.column_context:
            statistical = null_task.inputs.column_context[column].statistical
            dtype = statistical.get("dtype")
            if dtype:
                return str(dtype).lower()
        return "unknown"

    @staticmethod
    def _strategy_supported_by_final_dtype(strategy: str, final_dtype: str) -> bool:
        if strategy not in {"fill_mean", "fill_median"}:
            return True
        numeric_or_temporal_markers = (
            "int", "float", "double", "number", "decimal", "date", "datetime",
        )
        return any(marker in final_dtype for marker in numeric_or_temporal_markers)

    @staticmethod
    def _semantic_columns_dict(semantic_profile: Any | None) -> dict[str, Any]:
        if semantic_profile is None:
            return {}
        if isinstance(semantic_profile, dict):
            return semantic_profile.get("columns") or {}
        return getattr(semantic_profile, "columns", {}) or {}

    @staticmethod
    def _detail_value(detail: Any, key: str, default: Any) -> Any:
        if isinstance(detail, dict):
            return detail.get(key, default)
        return getattr(detail, key, default)

    def _build_dedup_review_section(self, task: TaskDetail) -> ReviewSection:
        strategy = self._strategy_dict(task)
        primary_keys = list(strategy.get("primary_keys") or task.columns)
        identifier_columns = list(strategy.get("identifier_columns") or primary_keys)
        ignored_columns = list(strategy.get("ignored_columns") or [])
        keep_rule = self._planner_keep_rule(strategy)
        dedup_mode = self._planner_dedup_mode(strategy)
        fuzzy_enabled = bool((strategy.get("fuzzy_matching") or {}).get("enabled"))

        return ReviewSection(
            task_id=task.task_id,
            title="Deduplication",
            fields=[
                ReviewField(
                    field_key="mode",
                    label="Dedup mode",
                    value=dedup_mode,
                    editable=False,
                    input_type="readonly",
                    help_text="Planner-selected broad deduplication mode.",
                ),
                ReviewField(
                    field_key="key_columns",
                    label="Key columns",
                    value=primary_keys,
                    editable=True,
                    input_type="multiselect",
                    help_text="Columns that define the same entity or record.",
                ),
                ReviewField(
                    field_key="identifier_columns",
                    label="Identifier columns",
                    value=identifier_columns,
                    editable=True,
                    input_type="multiselect",
                    help_text="Columns the planner considers strong or supporting identifiers.",
                ),
                ReviewField(
                    field_key="ignored_columns",
                    label="Ignored columns",
                    value=ignored_columns,
                    editable=True,
                    input_type="multiselect",
                    help_text="Columns that should not drive deduplication decisions.",
                ),
                ReviewField(
                    field_key="keep_rule",
                    label="Keep rule",
                    value=keep_rule,
                    editable=True,
                    input_type="select",
                    options=["keep_most_complete", "keep_first", "keep_last"],
                    help_text="How to choose the survivor row within each duplicate group.",
                ),
                ReviewField(
                    field_key="fuzzy_enabled",
                    label="Fuzzy candidate generation",
                    value=fuzzy_enabled,
                    editable=True,
                    input_type="boolean",
                    help_text="Whether planner enabled fuzzy candidate generation for this task.",
                ),
            ],
        )

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
    def _planner_dedup_mode(strategy: dict[str, Any]) -> str:
        primary_keys = strategy.get("primary_keys") or []
        exact_match = strategy.get("exact_match") or {}
        if primary_keys:
            return "exact_key"
        if exact_match.get("enabled"):
            return "exact_full_row"
        return "exact_full_row"
