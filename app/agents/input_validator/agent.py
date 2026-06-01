"""Input Validator Agent — uses LLM to analyze the EDA profile and validate the dataset."""
import json
import logging
from typing import Any
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.agents.input_validator.prompts import INPUT_VALIDATOR_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class ClarificationQuestion(BaseModel):
    question: str = Field(description="The multiple-choice question asking for clarification.")
    options: list[str] = Field(
        description="Exactly 3 distinct options for the user to choose from.",
        min_items=3,
        max_items=3
    )

class ValidationResult(BaseModel):
    """Structured output expected from the Input Validator LLM."""

    intent_description: str = Field(
        description="A description of what the user wants to achieve based on their prompt and the actual dataset EDA profile."
    )
    clarification_questions: list[ClarificationQuestion] = Field(
        default_factory=list,
        description="A list of about 3 multiple-choice questions to clarify data cleaning decisions."
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
        
        # Use structured output
        try:
            structured_llm = self.llm.with_structured_output(ValidationResult)
            response: ValidationResult = await structured_llm.ainvoke(messages)
        except Exception as e:
            logger.warning(f"Structured output failed: {e}. Falling back to raw LLM and manual JSON parsing...")
            
            # Request raw JSON strictly
            messages_fallback = messages + [
                SystemMessage(content="CRITICAL: You must output ONLY a valid JSON object matching the ValidationResult schema. Do NOT wrap the response in markdown code blocks like ```json ... ```, and do NOT add any trailing characters or conversational text.")
            ]
            raw_response = await self.llm.ainvoke(messages_fallback)
            content = raw_response.content
            
            # Clean up the output string
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

        logger.info("InputValidatorAgent successfully parsed structured output.")

        # Format the response into a JSON string for the message, 
        # and also put the raw dict into state for the frontend to consume.
        json_data = response.model_dump()
        final_message = json.dumps(json_data, ensure_ascii=False, indent=2)

        # Update state based on decision
        updates: dict[str, Any] = {
            "messages": [AIMessage(content=final_message, name=self.name)],
            "input_validation_result": json_data,
            "next_node": "end" # Pause for human input
        }

        return updates
