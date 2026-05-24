"""Reporter Agent — compiles and saves the final pipeline report."""
from app.agents.base import BaseAgent
from app.agents.registry import AgentRegistry
from app.agents.reporter.prompts import REPORTER_SYSTEM_PROMPT
from app.core.llm_factory import create_llm
from app.core.logging import get_logger
from app.graphs.states.graph_state import AgentState
from app.models.schemas.agent import AgentOutput
from app.tools.registry import REPORTER_TOOLS

logger = get_logger(__name__)


@AgentRegistry.auto_register
class ReporterAgent(BaseAgent):
    """Generates the final pipeline report and persists it to disk.

    Aggregates the results from all previous pipeline stages (profiling,
    cleaning, validation, transformation) into a structured, human-readable
    report saved via the save_to_file tool.
    """

    name = "reporter"
    description = "Generates and saves the final data quality report summarising all pipeline stages"

    def __init__(self) -> None:
        self.llm = create_llm().bind_tools(REPORTER_TOOLS)

    async def run(self, state: AgentState) -> AgentOutput:
        """Compile results from all stages and save the final report.

        TODO: Implement full ReAct tool-calling loop.
        """
        # TODO: Replace with full LangChain agent executor / ReAct loop
        logger.info("Reporter agent running", job_id=state.get("job_id"))
        return AgentOutput(
            agent_name=self.name,
            success=True,
            data={"status": "TODO: implement reporting logic"},
        )
