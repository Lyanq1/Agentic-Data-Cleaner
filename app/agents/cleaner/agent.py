"""Cleaner Agent — handles nulls, duplicates, and outliers in the dataset."""
from app.agents.base import BaseAgent
from app.agents.cleaner.prompts import CLEANER_SYSTEM_PROMPT
from app.agents.registry import AgentRegistry
from app.core.llm_factory import create_llm
from app.core.logging import get_logger
from app.graphs.states.graph_state import AgentState
from app.models.schemas.agent import AgentOutput
from app.tools.registry import CLEANER_TOOLS

logger = get_logger(__name__)


@AgentRegistry.auto_register
class CleanerAgent(BaseAgent):
    """Cleans the dataset by removing nulls, duplicates, and outliers.

    Applies rule-based and LLM-guided cleaning strategies to produce
    a clean version of the input dataset.
    """

    name = "cleaner"
    description = "Handles missing values, removes duplicates, and treats outliers in the dataset"

    def __init__(self) -> None:
        self.llm = create_llm().bind_tools(CLEANER_TOOLS)

    async def run(self, state: AgentState) -> AgentOutput:
        """Clean the dataset at state['file_path'] using defined rules.

        TODO: Implement full ReAct tool-calling loop.
        """
        # TODO: Replace with full LangChain agent executor / ReAct loop
        logger.info("Cleaner agent running", file_path=state.get("file_path"))
        return AgentOutput(
            agent_name=self.name,
            success=True,
            data={"status": "TODO: implement cleaning logic"},
        )
