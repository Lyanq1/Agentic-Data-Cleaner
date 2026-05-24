"""Profiler Agent — reads and profiles the input dataset."""
from app.agents.base import BaseAgent
from app.agents.profiler.prompts import PROFILER_SYSTEM_PROMPT
from app.agents.registry import AgentRegistry
from app.core.llm_factory import create_llm
from app.core.logging import get_logger
from app.graphs.states.graph_state import AgentState
from app.models.schemas.agent import AgentOutput
from app.tools.registry import PROFILER_TOOLS

logger = get_logger(__name__)


@AgentRegistry.auto_register
class ProfilerAgent(BaseAgent):
    """Profiles the input dataset: schema, statistics, data quality metrics."""

    name = "profiler"
    description = "Analyzes dataset schema, missing values, type distributions, and outliers"

    def __init__(self) -> None:
        self.llm = create_llm().bind_tools(PROFILER_TOOLS)

    async def run(self, state: AgentState) -> AgentOutput:
        """Profile the dataset at state['file_path'].

        TODO: Implement full ReAct tool-calling loop.
        """
        # TODO: Replace with full LangChain agent executor / ReAct loop
        logger.info("Profiler agent running", file_path=state.get("file_path"))
        return AgentOutput(
            agent_name=self.name,
            success=True,
            data={"status": "TODO: implement profiling logic"},
        )
