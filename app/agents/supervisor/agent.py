"""Supervisor Agent — routes to worker agents using LLM decision."""
import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.base import AgentOutput, BaseAgent
from app.agents.registry import AgentRegistry
from app.agents.supervisor.prompts import SUPERVISOR_SYSTEM_PROMPT
from app.graphs.states.global_state import AgentState
from app.agents.base import AgentOutput


@AgentRegistry.auto_register
class SupervisorAgent(BaseAgent):
    """LLM-based supervisor that decides which agent runs next.

    Does not use tools — the LLM responds with a JSON routing decision.
    The ``tools`` list is empty so the LLM is created unbound by ``BaseAgent``.
    """

    name = "supervisor"
    description = "Orchestrates worker agents by analyzing state and deciding the next action"
    # No tools — supervisor uses pure LLM reasoning (tools = [] inherited from BaseAgent)

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
            return AgentOutput(
                agent_name=self.name,
                success=True,
                data={"reasoning": decision.get("reasoning")},
                next_agent=next_agent,
            )
        except (json.JSONDecodeError, KeyError) as e:
            return AgentOutput(
                agent_name=self.name,
                success=False,
                error=str(e),
                next_agent=None,
            )
