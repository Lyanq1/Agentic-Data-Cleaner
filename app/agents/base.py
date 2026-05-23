"""Abstract base class for all agents."""
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from app.models.schemas.agent import AgentInput, AgentOutput

if TYPE_CHECKING:
    from app.graphs.state import AgentState


class BaseAgent(ABC):
    """Base class all worker agents must inherit.

    Subclasses must implement `run()`. Optionally override `astream()`
    for token-level streaming support.

    Example::

        class MyAgent(BaseAgent):
            name = "my_agent"
            description = "Does something useful"

            async def run(self, state: AgentState) -> AgentOutput:
                ...
    """

    # Subclasses MUST set these class-level attributes
    name: str = "base_agent"
    description: str = "Override this in subclasses"

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
