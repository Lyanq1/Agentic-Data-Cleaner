"""Abstract base class for all agents."""
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.graphs.states.graph_state import AgentState


class BaseAgent(ABC):
    # Subclasses MUST set these class-level attributes
    name: str = "base_agent"
    description: str = "Override this in subclasses"

    # Subclasses MAY override this to bind tools
    tools: list = []

    def __init__(self) -> None:
        """Build the LLM and bind tools declared in ``self.tools``."""
        from app.core.llm_factory import get_llm_factory
        self.llm = get_llm_factory().create_with_tools(self.tools)

    @abstractmethod
    async def run(self, state: "AgentState") -> AgentOutput:
        """Execute the agent logic given the current graph state.

        Args:
            state: Current AgentState snapshot.

        Returns:
            AgentOutput with results and optional routing hint.
        """
        ...

    async def astream(self, state: "AgentState"):
        """Stream agent output token-by-token (optional, override in subclasses).

        By default falls back to run().
        """
        result = await self.run(state)
        yield result
