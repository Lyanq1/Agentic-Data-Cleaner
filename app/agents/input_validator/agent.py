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
                "convert them into metadata cleaning rules, combine them with the semantic and statistical profiles, "
                "and output the final JSON matching the InputValidationResult schema with status = 'ready'. "
                "Do NOT set status to 'needs_clarification'. You must set status to 'ready'. "
                "Make sure to populate the 'action_plan' dictionary with the cleaning plans for 'null', 'duplicate', and 'typecast'. "
                "Populate 'resolved_by_user' list with the resolved issue/column descriptions. "
                "Also, keep the exact same 'clarifications' structure but fill in the 'answer' field of each question with the user's actual selected answer. "
                "CRITICAL for Q4_allow_missing_confirmation: populate its 'answer' field as a JSON object (dict) mapping "
                "EVERY column name in the dataset to a boolean (true/false) reflecting the user's confirmed allow_missing decision. "
                "Example: {\"TITLE\": false, \"CONTRIBUTORS\": true, \"BARCODE\": false, ...}. "
                "If the user agreed with the AI's suggestion, preserve the original allow_missing values from the Semantic Profile. "
                "If the user corrected any column, apply their correction. "
                "Do NOT leave Q4_allow_missing_confirmation.answer as null."
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
        json_data = response.model_dump()
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

        # Locate Q4 answer inside clarifications.null
        clarifications = validation_result.clarifications
        if clarifications is None or clarifications.null is None:
            return None

        q4 = clarifications.null.Q4_allow_missing_confirmation
        if q4 is None or q4.answer is None:
            return None

        # q4.answer is dict[str, bool]: {"TITLE": False, "CONTRIBUTORS": True, ...}
        patched = False
        for col_name, new_value in q4.answer.items():
            if col_name in profile.columns:
                profile.columns[col_name].allow_missing = bool(new_value)
                logger.info(
                    "InputValidatorAgent: %s.allow_missing overridden to %s by user.",
                    col_name,
                    new_value,
                )
                patched = True

        return profile if patched else None
