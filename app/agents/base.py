"""Abstract base class for all agents."""
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.graphs.states.graph_state import AgentState


class BaseAgent(ABC):
    """Base class all worker agents must inherit.

    - Subclasses must implement ``run()``.
    - The default ``__init__`` builds a configured LLM and binds ``tools`` automatically — subclasses only need
    to declare the class-level ``tools`` list (empty by default).

    Optionally override ``astream()`` for token-level streaming support.

    Example::
        class MyAgent(BaseAgent):
            name = "my_agent"
            description = "Does something useful"
            tools = [my_tool_a, my_tool_b]  # bound automatically

            async def run(self, state: AgentState) -> AgentOutput:
                result = await self.llm.ainvoke(...)
                ...
    """

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
