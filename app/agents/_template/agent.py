"""Template Agent — copy and customize to create a new agent.

DO NOT register this template agent (it is not in AgentRegistry by default).
"""
from app.agents.base import BaseAgent
from app.core.llm_factory import create_llm
from app.core.logging import get_logger
from app.graphs.state import AgentState
from app.models.schemas.agent import AgentOutput

logger = get_logger(__name__)


class TemplateAgent(BaseAgent):
    """TODO: Replace this docstring with a description of your agent."""

    name = "template_agent"  # TODO: rename — must be unique
    description = "TODO: describe what this agent does"  # Used by Supervisor

    def __init__(self) -> None:
        # TODO: bind your tools here
        # from app.tools.registry import YOUR_AGENT_TOOLS
        # self.llm = create_llm().bind_tools(YOUR_AGENT_TOOLS)
        self.llm = create_llm()

    async def run(self, state: AgentState) -> AgentOutput:
        """TODO: implement your agent logic here.

        Args:
            state: Current AgentState snapshot.

        Returns:
            AgentOutput with results. Set next_agent to route directly,
            or leave None to let the supervisor decide.
        """
        logger.info("TemplateAgent running", job_id=state.get("job_id"))
        # TODO: implement tool-calling loop
        return AgentOutput(
            agent_name=self.name,
            success=True,
            data={"status": "TODO: implement"},
            next_agent=None,  # Let supervisor decide
        )
