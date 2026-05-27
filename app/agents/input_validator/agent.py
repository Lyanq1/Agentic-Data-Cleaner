"""Input Validator Agent — uses LLM to analyze the EDA profile and validate the dataset."""
import json
import logging
from typing import Any
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.agents.input_validator.prompts import INPUT_VALIDATOR_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class ValidationResult(BaseModel):
    """Structured output expected from the Input Validator LLM."""

    is_sufficient_context: bool = Field(
        description="True if the user's intent and data context are clear enough to proceed. False if you must ask the user for clarification."
    )
    message: str = Field(
        description="The message to show to the user. If is_sufficient_context=False, this must be a clarifying question. If True, a summary of the plan."
    )
    suggested_cleaning_steps: list[str] = Field(
        default_factory=list,
        description="List of concrete technical cleaning steps to execute (if is_sufficient_context=True)."
    )


class InputValidatorAgent(BaseAgent):
    """Analyzes the statistical EDA profile of a dataset via the LLM.

    Reads ``data_profile`` and conversation history from GlobalState, 
    evaluates if the context is sufficient, and returns a structured decision.
    """

    name = "input_validator"
    description = "Validates dataset quality against user intent and asks for clarification if needed."
    tools = []  # pure LLM reasoning

    async def run(self, state: dict) -> dict[str, Any]:
        """Invoke the LLM with structured output."""
        data_profile = state.get("data_profile")
        user_prompt = state.get("user_prompt", "")
        # Get prior messages in case this is a continuation of a conversation
        prior_messages = state.get("messages", [])

        if not data_profile:
            logger.warning("InputValidatorAgent: no data_profile found in state.")
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

        logger.info(f"InputValidatorAgent result: sufficient_context={response.is_sufficient_context}")

        # Update state based on decision
        updates: dict[str, Any] = {
            "messages": [AIMessage(content=response.message, name=self.name)]
        }

        if response.is_sufficient_context:
            updates["cleaning_plan"] = response.suggested_cleaning_steps
            # Transition to the next logical step (e.g., planner or end for now)
            updates["next_node"] = "end" 
        else:
            # We need human input. The graph should stop here.
            # Setting next_node to "end" stops execution so the user can reply.
            # In a real HITL, you might route to a "human_node".
            updates["next_node"] = "end"

        return updates
