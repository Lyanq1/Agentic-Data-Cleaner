"""Validator Agent — validates the dataset against business rules and constraints."""
from app.agents.base import BaseAgent
from app.agents.registry import AgentRegistry
from app.agents.validator.prompts import VALIDATOR_SYSTEM_PROMPT
from app.core.llm_factory import create_llm
from app.core.logging import get_logger
from app.graphs.states.graph_state import AgentState
from app.models.schemas.agent import AgentOutput
from app.tools.registry import VALIDATOR_TOOLS

logger = get_logger(__name__)


@AgentRegistry.auto_register
class ValidatorAgent(BaseAgent):
    """Validates the dataset against user-defined business rules and constraints.

    Checks schema integrity, value constraints, allowed ranges, regex patterns,
    and referential integrity rules. Produces a detailed validation report.
    """

    name = "validator"
    description = "Validates data against business rules, constraints, and schema requirements"

    def __init__(self) -> None:
        self.llm = create_llm().bind_tools(VALIDATOR_TOOLS)

    async def run(self, state: AgentState) -> AgentOutput:
        """Validate the dataset at state['file_path'] against state['rules'].

        TODO: Implement full ReAct tool-calling loop.
        """
        # TODO: Replace with full LangChain agent executor / ReAct loop
        logger.info("Validator agent running", file_path=state.get("file_path"))
        return AgentOutput(
            agent_name=self.name,
            success=True,
            data={"status": "TODO: implement validation logic"},
        )
