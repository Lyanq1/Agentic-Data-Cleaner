"""Input Validator Agent — uses LLM to analyze the EDA profile and validate the dataset."""
import json
import logging
from typing import Any, Literal
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage


from app.agents.base import BaseAgent
from app.agents.input_validator.prompts import INPUT_VALIDATOR_SYSTEM_PROMPT
from app.graphs.states.global_state import GlobalState
from app.graphs.states.input_validation import (
    InputValidationResult,
    NullClarifications,
    StrategyQuestion,
    ClarificationIssues,
)
from app.graphs.states.profiles import SemanticProfile


logger = logging.getLogger(__name__)

class InputValidatorAgent(BaseAgent):
    """Analyzes the statistical EDA profile of a dataset via the LLM.

    Reads ``statistical_profile`` and conversation history from GlobalState, 
    evaluates if the context is sufficient, and returns a structured decision.
    """

    name = "input_validator"
    description = "Validates dataset quality against user intent and asks for clarification if needed."
    tools = []  # pure LLM reasoning

    async def run(self, state: GlobalState) -> dict[str, Any]:
        """Invoke the LLM with structured output."""
        data_profile = state.get("statistical_profile")
        semantic_profile = state.get("semantic_profile")
        user_prompt = state.get("user_prompt", "")
        # Get prior messages in case this is a continuation of a conversation
        prior_messages = state.get("messages", [])

        # Pre-process user-submitted custom strategy datetime strings to ISO format
        val_result = state.get("input_validation_result")
        if val_result:
            if hasattr(val_result, "clarifications") and val_result.clarifications:
                clar_obj = val_result.clarifications
                for cat in ["null", "duplicate", "typecast"]:
                    cat_data = getattr(clar_obj, cat, None)
                    if cat_data:
                        fields_dict = getattr(cat_data, "__dict__", {}) or {}
                        extra_dict = getattr(cat_data, "model_extra", {}) or {}
                        all_fields = {**fields_dict, **extra_dict}
                        for q_key, q_val in all_fields.items():
                            if q_key.startswith("Q2_strategy_column_") and q_val:
                                col_name = q_key[len("Q2_strategy_column_"):]
                                expected_type = "str"
                                if semantic_profile:
                                    if hasattr(semantic_profile, "columns"):
                                        col_detail = semantic_profile.columns.get(col_name)
                                        if col_detail:
                                            expected_type = getattr(col_detail, "expected_type", "str")
                                    elif isinstance(semantic_profile, dict) and "columns" in semantic_profile:
                                        col_detail = semantic_profile["columns"].get(col_name)
                                        if col_detail:
                                            expected_type = col_detail.get("expected_type", "str")
                                
                                if expected_type in ("datetime", "date"):
                                    answer = None
                                    if isinstance(q_val, dict):
                                        answer = q_val.get("answer")
                                    elif hasattr(q_val, "answer"):
                                        answer = getattr(q_val, "answer")
                                    
                                    if answer and not answer.lower().startswith("keep_null"):
                                        prefix = ""
                                        ans_stripped = answer.strip()
                                        while True:
                                            matched = False
                                            lower_ans = ans_stripped.lower()
                                            for p in ["custom strategy:", "fill_value:", "fill_value ", "fill ", "impute "]:
                                                if lower_ans.startswith(p):
                                                    idx = len(p)
                                                    prefix += ans_stripped[:idx]
                                                    ans_stripped = ans_stripped[idx:].strip()
                                                    matched = True
                                                    break
                                            if not matched:
                                                break
                                        
                                        from dateutil import parser
                                        try:
                                            dt = parser.parse(ans_stripped, dayfirst=True)
                                            if expected_type == "date":
                                                iso_val = dt.date().isoformat()
                                            else:
                                                iso_val = dt.isoformat()
                                            cleaned_answer = f"{prefix}{iso_val}"
                                            
                                            if isinstance(q_val, dict):
                                                q_val["answer"] = cleaned_answer
                                            elif hasattr(q_val, "answer"):
                                                setattr(q_val, "answer", cleaned_answer)
                                        except Exception:
                                            pass
            elif isinstance(val_result, dict) and "clarifications" in val_result:
                clar_dict = val_result["clarifications"]
                if clar_dict:
                    for cat in ["null", "duplicate", "typecast"]:
                        cat_data = clar_dict.get(cat)
                        if isinstance(cat_data, dict):
                            for q_key, q_val in cat_data.items():
                                if q_key.startswith("Q2_strategy_column_") and isinstance(q_val, dict):
                                    col_name = q_key[len("Q2_strategy_column_"):]
                                    expected_type = "str"
                                    if semantic_profile:
                                        if hasattr(semantic_profile, "columns"):
                                            col_detail = semantic_profile.columns.get(col_name)
                                            if col_detail:
                                                expected_type = getattr(col_detail, "expected_type", "str")
                                        elif isinstance(semantic_profile, dict) and "columns" in semantic_profile:
                                            col_detail = semantic_profile["columns"].get(col_name)
                                            if col_detail:
                                                expected_type = col_detail.get("expected_type", "str")
                                    
                                    if expected_type in ("datetime", "date"):
                                        answer = q_val.get("answer")
                                        if answer and not answer.lower().startswith("keep_null"):
                                            prefix = ""
                                            ans_stripped = answer.strip()
                                            while True:
                                                matched = False
                                                lower_ans = ans_stripped.lower()
                                                for p in ["custom strategy:", "fill_value:", "fill_value ", "fill ", "impute "]:
                                                    if lower_ans.startswith(p):
                                                        idx = len(p)
                                                        prefix += ans_stripped[:idx]
                                                        ans_stripped = ans_stripped[idx:].strip()
                                                        matched = True
                                                        break
                                                if not matched:
                                                    break
                                            
                                            from dateutil import parser
                                            try:
                                                dt = parser.parse(ans_stripped, dayfirst=True)
                                                if expected_type == "date":
                                                    iso_val = dt.date().isoformat()
                                                else:
                                                    iso_val = dt.isoformat()
                                                q_val["answer"] = f"{prefix}{iso_val}"
                                            except Exception:
                                                pass

        if not data_profile:
            logger.warning("InputValidatorAgent: no statistical_profile found in state.")
            return {
                "messages": [
                    AIMessage(
                        content="⚠️ No data profile available to validate. "
                        "Please ensure the profiler node ran successfully.",
                        name=self.name,
                    )
                ],
            }

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
        if semantic_profile_dict and "thinking" in semantic_profile_dict:
            # Remove thinking field to reduce token usage and avoid confusing the LLM parser
            del semantic_profile_dict["thinking"]

        human_content = (
            f"## User Instruction\n{user_prompt}\n\n"
            f"## Dataset EDA Profile\n```json\n{json.dumps(data_profile_dict, indent=2, default=str)}\n```\n"
        )
        if semantic_profile_dict:
            human_content += f"\n## Dataset Semantic Profile\n```json\n{json.dumps(semantic_profile_dict, indent=2, default=str)}\n```\n"

        messages = [
            SystemMessage(content=INPUT_VALIDATOR_SYSTEM_PROMPT),
            HumanMessage(content=human_content),
        ]
        
        # Append any prior conversation history so the LLM remembers previous answers
        # (Exclude system/tool messages if needed, but adding all is fine for now)
        for msg in prior_messages:
            if isinstance(msg, (HumanMessage, AIMessage)):
                messages.append(msg)

        # Check if the user has already provided answers to the clarifications
        is_answered = False
        val_result = state.get("input_validation_result")
        if val_result:
            clarifications = val_result.get("clarifications") if isinstance(val_result, dict) else getattr(val_result, "clarifications", None)
            if clarifications:
                if hasattr(clarifications, "model_dump"):
                    clar_dict = clarifications.model_dump()
                elif hasattr(clarifications, "dict"):
                    clar_dict = clarifications.dict()
                else:
                    clar_dict = clarifications

                has_questions = False
                all_filled = True
                for cat in ["null", "duplicate", "typecast"]:
                    cat_data = clar_dict.get(cat) if clar_dict else None
                    if cat_data:
                        for _, q in cat_data.items():
                            if q:
                                has_questions = True
                                if q.get("answer") is None:
                                    all_filled = False
                if has_questions and all_filled:
                    is_answered = True

        if is_answered:
            messages.append(SystemMessage(content=(
                "USER HAS PROVIDED ANSWERS to the clarification questions. "
                "You must now read the user's answers in the chat history, "
                "convert them into metadata cleaning rules, and combine them with the semantic and statistical profiles. "
                "CRITICAL: You MUST check if the user's answers and requirements are feasible according to STEP 3 — UNFEASIBLE SCENARIOS. "
                "For example, the user must not request mean/median imputation on non-numeric columns, "
                "impute nulls on columns with no nulls, cast non-date strings to datetime, or provide invalid/incompatible custom fill values. "
                "If any user answer is unfeasible or conflicts with the dataset constraints, you MUST: "
                "1. Set status = 'needs_clarification'. "
                "2. Clear the 'answer' field of that specific unfeasible question to null so the user can re-answer. "
                "3. Set the 'error' field of that question with a clear explanation of why it was unfeasible (e.g., 'The custom strategy \"fill abc\" is invalid because this is a datetime column, not string. Please provide a valid ISO datetime format.'). "
                "4. Set the 'previous_answer' field of that question to the exact user answer they submitted (e.g., 'Custom strategy: fill abc'). "
                "5. Keep the valid answers for other questions in their 'answer' field (leaving 'error' and 'previous_answer' as null for valid questions). "
                "Only if ALL user answers are feasible, you must: "
                "1. Set status = 'ready'. "
                "2. Populate the 'action_plan' dictionary with the cleaning plans for 'null', 'duplicate', and 'typecast'. "
                "3. Populate 'resolved_by_user' list with the resolved issue/column descriptions. "
                "4. Keep the exact same 'clarifications' structure but fill in the 'answer' field of each question with the user's actual selected answer. "
                "5. For each Q1_allow_missing_column_<name>, populate its 'answer' field with the user's confirmed answer ('Yes' or 'No') based on their choices."
            )))


        logger.info("InputValidatorAgent: invoking LLM for structured dataset validation...")
        
        # Use JSON mode instead of structured function calling to strictly follow Prompt-based design
        messages.append(SystemMessage(content="CRITICAL: You must output ONLY a valid JSON object matching the requested schema. Do NOT wrap the response in markdown code blocks like ```json ... ```, and do NOT add any trailing characters or conversational text."))
        
        content_clean = None
        try:
            # Bind response_format to enforce JSON output
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
                
            response = InputValidationResult.model_validate_json(content_clean)
        except Exception as e:
            logger.error(f"Failed to parse LLM JSON output: {e}")
            print(f"\n[DEBUG ERROR] JSON parsing / validation failed: {e}")
            print(f"[DEBUG ERROR] Cleaned Content received:\n{content_clean}\n")
            # Fallback to a safe error state
            response = InputValidationResult(
                status="needs_clarification",
                reasoning=f"The system encountered an error parsing the LLM's JSON output. Error: {e}",
                clarifications=ClarificationIssues(
                    null=NullClarifications(
                        Q1_strategy=StrategyQuestion(
                            question="The AI failed to format its response correctly. Would you like to retry or abort?",
                            options=["(Recommended) Retry analysis", "Abort analysis", "Provide new instructions"],
                            consequences={
                                "(Recommended) Retry analysis": "Retrying might succeed if it was a transient formatting issue.",
                                "Abort analysis": "The current run will stop.",
                                "Provide new instructions": "You can modify your instructions and retry."
                            }
                        )
                    )
                )
            )

        logger.info("InputValidatorAgent successfully parsed structured output.")

        # Format the response into a JSON string for the message, 
        # and also put the raw dict into state for the frontend to consume.
        json_data = response.model_dump(exclude_none=True)
        final_message = json.dumps(json_data, ensure_ascii=False, indent=2)

        # ------------------------------------------------------------------
        # Apply Q4 allow_missing overrides to semantic_profile
        # When user has confirmed/corrected which columns can be null,
        # patch semantic_profile.columns[col].allow_missing with the answer.
        # ------------------------------------------------------------------
        semantic_profile_update: SemanticProfile | None = None
        if is_answered:
            semantic_profile_update = self._apply_allow_missing_overrides(
                state.get("semantic_profile"), response
            )

        # Update state based on decision
        next_node = "planner" if response.status == "ready" else "end"
        updates: dict[str, Any] = {
            "messages": [AIMessage(content=final_message, name=self.name)],
            "input_validation_result": json_data,
            "next_node": next_node,
        }
        if semantic_profile_update is not None:
            updates["semantic_profile"] = semantic_profile_update
            logger.info(
                "InputValidatorAgent: semantic_profile.allow_missing updated from Q4 user answer."
            )

        return updates

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_allow_missing_overrides(
        raw_semantic_profile: Any,
        validation_result: InputValidationResult,
    ) -> "SemanticProfile | None":  # noqa: F821
        """Patch semantic_profile.columns[col].allow_missing from Q4 user answer.

        Returns the updated SemanticProfile, or None if there is nothing to patch.
        """
        if raw_semantic_profile is None:
            return None

        # Coerce to SemanticProfile
        try:
            if hasattr(raw_semantic_profile, "model_dump"):
                profile = SemanticProfile.model_validate(raw_semantic_profile.model_dump())
            elif isinstance(raw_semantic_profile, dict):
                profile = SemanticProfile.model_validate(raw_semantic_profile)
            else:
                return None
        except Exception:
            return None

        # Locate Q1 answers inside clarifications.null
        clarifications = validation_result.clarifications
        if clarifications is None or clarifications.null is None:
            return None

        # clarifications.null can be a dict or a BaseModel
        if isinstance(clarifications.null, dict):
            null_dict = clarifications.null
        else:
            null_dict = clarifications.null.model_dump() if hasattr(clarifications.null, "model_dump") else clarifications.null.__dict__

        patched = False

        # Individual column yes/no questions: Q1_allow_missing_column_<col_name>
        for k, v in null_dict.items():
            if k.startswith("Q1_allow_missing_column_") and v:
                col_name = k[len("Q1_allow_missing_column_"):]
                if col_name in profile.columns:
                    answer = v.get("answer") if isinstance(v, dict) else getattr(v, "answer", None)
                    if answer in ("Yes", "No"):
                        new_val = (answer == "Yes")
                        profile.columns[col_name].allow_missing = new_val
                        logger.info(
                            "InputValidatorAgent: %s.allow_missing overridden to %s by user.",
                            col_name,
                            new_val,
                        )
                        patched = True

        return profile if patched else None
