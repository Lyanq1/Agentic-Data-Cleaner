"""Abstract base class and shared types for all agents."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING
from app.core.llm_factory import create_llm

if TYPE_CHECKING:
    from app.graphs.states.global_state import GlobalState

@dataclass
class AgentOutput:
    """Standard output returned by every agent's ``run()`` method."""

    agent_name: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    next_agent: str | None = None  # routing hint for the supervisor
    error: str | None = None


class BaseAgent(ABC):
    """Base class that all agents inherit from."""

    # Subclasses MUST set these class-level attributes
    name: str = "base_agent"
    description: str = "Override this in subclasses"

    # Subclasses MAY override this to bind tools
    tools: list = []

    def __init__(self) -> None:
        """Build the LLM and optionally bind tools declared in ``self.tools``."""

        base_llm = create_llm()
        if self.tools:
            self.llm = base_llm.bind_tools(self.tools)
        else:
            self.llm = base_llm

    @abstractmethod
    async def run(self, state: "GlobalState") -> dict:
        """Execute the agent logic given the current graph state.

        Args:
            state: Current GlobalState snapshot.

        Returns:
            A dict of state updates to merge back into GlobalState.
        """
        ...
