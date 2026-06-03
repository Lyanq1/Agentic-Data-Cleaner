"""Input Validator Agent — uses LLM to analyze the EDA profile and validate the dataset."""
import json
import logging
from typing import Any, Literal
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from pydantic import BaseModel, Field, field_validator

from app.agents.base import BaseAgent
from app.agents.input_validator.prompts import INPUT_VALIDATOR_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class StrategyQuestion(BaseModel):
    question: str = Field(description="The strategy question text.")
    options: list[str] = Field(description="Exactly 3 distinct options.")
    consequences: str | None = Field(default=None, description="Consequences of each option.")

class InsightQuestion(BaseModel):
    question: str = Field(description="The insight question text.")
    insight: str = Field(description="The semantic insight revealed.")
    confirm: str = Field(description="The yes/no confirmation ask.")

class NullClarifications(BaseModel):
    Q1_strategy: StrategyQuestion | None = None
    Q2_semantic_insight: InsightQuestion | None = None
    Q3_semantic_insight: InsightQuestion | None = None

class DuplicateClarifications(BaseModel):
    Q1_strategy: StrategyQuestion | None = None
    Q2_semantic_insight: InsightQuestion | None = None
    Q3_semantic_insight: InsightQuestion | None = None

class TypecastClarifications(BaseModel):
    Q1_semantic_insight: InsightQuestion | None = None
    Q2_semantic_insight: InsightQuestion | None = None
    Q3_semantic_insight: InsightQuestion | None = None

class ClarificationIssues(BaseModel):
    null: NullClarifications | None = None
    duplicate: DuplicateClarifications | None = None
    typecast: TypecastClarifications | None = None

class ActionPlan(BaseModel):
    null: str | None = None
    duplicate: str | None = None
    typecast: str | None = None

    @field_validator("null", "duplicate", "typecast", mode="before")
    @classmethod
    def convert_to_string(cls, v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            return " | ".join(f"{k}: {val}" for k, val in v.items())
        if isinstance(v, list):
            return ", ".join(str(item) for item in v)
        return str(v)

class ValidationResult(BaseModel):
    """Structured output expected from the Input Validator LLM."""
    status: Literal["ready", "needs_clarification"] = Field(
        description="The status of the validation. 'ready' or 'needs_clarification'."
    )
    reasoning: str = Field(
        description="Brief reasoning explaining the status."
    )
    resolved_by_user: list[str] = Field(
        default_factory=list,
        description="List of issues and columns resolved by the user's request."
    )
    action_plan: ActionPlan | None = Field(
        default=None,
        description="The plan for each issue if status is 'ready'."
    )
    clarifications: ClarificationIssues | None = Field(
        default=None,
        description="Clarifications needed per active issue if status is 'needs_clarification'."
    )


class InputValidatorAgent(BaseAgent):
    """Analyzes the statistical EDA profile of a dataset via the LLM.

    Reads ``statistical_profile`` and conversation history from GlobalState, 
    evaluates if the context is sufficient, and returns a structured decision.
    """

    name = "input_validator"
    description = "Validates dataset quality against user intent and asks for clarification if needed."
    tools = []  # pure LLM reasoning

    async def run(self, state: dict) -> dict[str, Any]:
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

        logger.info("InputValidatorAgent: invoking LLM for structured dataset validation...")
        
        # Use JSON mode instead of structured function calling to strictly follow Prompt-based design
        messages.append(SystemMessage(content="CRITICAL: You must output ONLY a valid JSON object matching the requested schema. Do NOT wrap the response in markdown code blocks like ```json ... ```, and do NOT add any trailing characters or conversational text."))
        
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
                
            response = ValidationResult.model_validate_json(content_clean)
        except Exception as e:
            logger.error(f"Failed to parse LLM JSON output: {e}")
            print(f"\n[DEBUG ERROR] JSON parsing / validation failed: {e}")
            print(f"[DEBUG ERROR] Cleaned Content received:\n{content_clean}\n")
            # Fallback to a safe error state
            response = ValidationResult(
                status="needs_clarification",
                reasoning=f"The system encountered an error parsing the LLM's JSON output. Error: {e}",
                clarifications=ClarificationIssues(
                    null=NullClarifications(
                        Q1_strategy=StrategyQuestion(
                            question="The AI failed to format its response correctly. Would you like to retry or abort?",
                            options=["(Recommended) Retry analysis", "Abort analysis", "Provide new instructions"],
                            consequences="Retrying might succeed if it was a transient formatting issue."
                        )
                    )
                )
            )

        logger.info("InputValidatorAgent successfully parsed structured output.")

        # Format the response into a JSON string for the message, 
        # and also put the raw dict into state for the frontend to consume.
        json_data = response.model_dump()
        final_message = json.dumps(json_data, ensure_ascii=False, indent=2)

        # Update state based on decision
        next_node = "planner" if response.status == "ready" else "end"
        updates: dict[str, Any] = {
            "messages": [AIMessage(content=final_message, name=self.name)],
            "input_validation_result": json_data,
            "next_node": next_node 
        }

        return updates
