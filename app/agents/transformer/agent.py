"""Transformer Agent — transforms and enriches the cleaned dataset."""
from app.agents.base import BaseAgent
from app.agents.registry import AgentRegistry
from app.agents.transformer.prompts import TRANSFORMER_SYSTEM_PROMPT
from app.core.llm_factory import create_llm
from app.core.logging import get_logger
from app.graphs.state import AgentState
from app.models.schemas.agent import AgentOutput
from app.tools.registry import TRANSFORMER_TOOLS

logger = get_logger(__name__)


@AgentRegistry.auto_register
class TransformerAgent(BaseAgent):
    """Transforms and enriches the cleaned dataset.

    Applies type casting, normalization, categorical encoding, and
    feature derivation according to the provided transformation rules.
    """

    name = "transformer"
    description = "Transforms and enriches data: type casting, normalization, encoding, and feature engineering"

    def __init__(self) -> None:
        self.llm = create_llm().bind_tools(TRANSFORMER_TOOLS)

    async def run(self, state: AgentState) -> AgentOutput:
        """Transform and enrich the cleaned dataset at state['file_path'].

        TODO: Implement full ReAct tool-calling loop.
        """
        # TODO: Replace with full LangChain agent executor / ReAct loop
        logger.info("Transformer agent running", file_path=state.get("file_path"))
        return AgentOutput(
            agent_name=self.name,
            success=True,
            data={"status": "TODO: implement transformation logic"},
        )
