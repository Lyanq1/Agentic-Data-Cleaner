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

        # Format profile
        profile_text = json.dumps(data_profile, indent=2, default=str)
        human_content = (
            f"## User Instruction\n{user_prompt}\n\n"
            f"## Dataset EDA Profile\n```json\n{profile_text}\n```"
        )

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
        structured_llm = self.llm.with_structured_output(ValidationResult)
        response: ValidationResult = await structured_llm.ainvoke(messages)

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
