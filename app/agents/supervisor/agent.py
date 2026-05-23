"""Supervisor Agent — routes to worker agents using LLM decision."""
import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.base import BaseAgent
from app.agents.registry import AgentRegistry
from app.agents.supervisor.prompts import SUPERVISOR_SYSTEM_PROMPT
from app.core.llm_factory import create_llm
from app.core.logging import get_logger
from app.graphs.state import AgentState
from app.models.schemas.agent import AgentOutput

logger = get_logger(__name__)


@AgentRegistry.auto_register
class SupervisorAgent(BaseAgent):
    """LLM-based supervisor that decides which agent runs next."""

    name = "supervisor"
    description = "Orchestrates worker agents by analyzing state and deciding the next action"

    def __init__(self) -> None:
        self.llm = create_llm()

    async def run(self, state: AgentState) -> AgentOutput:
        """Analyze current state and return next_agent routing decision."""
        available_agents = AgentRegistry.list_agents()
        prompt = SUPERVISOR_SYSTEM_PROMPT.format(
            available_agents=json.dumps(available_agents, indent=2),
            job_id=state.get("job_id", ""),
            file_path=state.get("file_path", ""),
            rules=json.dumps(state.get("rules", {}), indent=2),
            profile_result=json.dumps(state.get("profile_result"), indent=2),
            clean_result=json.dumps(state.get("clean_result"), indent=2),
            validation_result=json.dumps(state.get("validation_result"), indent=2),
            transform_result=json.dumps(state.get("transform_result"), indent=2),
            error=state.get("error"),
        )
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content="What should be the next step?"),
        ]
        response = await self.llm.ainvoke(messages)
        try:
            decision = json.loads(response.content)
            next_agent = decision.get("next_agent", "FINISH")
            if next_agent == "FINISH":
                next_agent = None
            logger.info(
                "Supervisor decision",
                next_agent=next_agent,
                reasoning=decision.get("reasoning"),
            )
            return AgentOutput(
                agent_name=self.name,
                success=True,
                data={"reasoning": decision.get("reasoning")},
                next_agent=next_agent,
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.error("Supervisor failed to parse LLM response", error=str(e))
            return AgentOutput(
                agent_name=self.name,
                success=False,
                error=str(e),
                next_agent=None,
            )
