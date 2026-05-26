"""AgentRegistry — central registry for discovering and instantiating agents.

How to register a new agent:
1. Create your agent class inheriting BaseAgent in a new folder under app/agents/
2. Call AgentRegistry.register(MyAgent) anywhere (e.g., in your agent's __init__.py)
   OR decorate with @AgentRegistry.auto_register

The Supervisor uses this registry to know which agents are available.
"""
from typing import TYPE_CHECKING, Type

from app.agents.base import BaseAgent

if TYPE_CHECKING:
    pass


class AgentRegistry:
    """Singleton registry mapping agent names to agent classes."""

    _registry: dict[str, Type[BaseAgent]] = {}

    @classmethod
    def register(cls, agent_class: Type[BaseAgent]) -> Type[BaseAgent]:
        """Register an agent class by its `name` attribute."""
        if not hasattr(agent_class, "name") or not agent_class.name:
            raise ValueError(
                f"{agent_class} must define a non-empty `name` class attribute"
            )
        cls._registry[agent_class.name] = agent_class
        return agent_class

    @classmethod
    def auto_register(cls, agent_class: Type[BaseAgent]) -> Type[BaseAgent]:
        """Decorator: automatically register an agent class.

        Usage::

            @AgentRegistry.auto_register
            class MyAgent(BaseAgent):
                name = "my_agent"
        """
        return cls.register(agent_class)

    @classmethod
    def get(cls, name: str) -> Type[BaseAgent]:
        """Retrieve an agent class by name.

        Raises:
            KeyError: if no agent with this name is registered.
        """
        if name not in cls._registry:
            raise KeyError(
                f"No agent registered with name '{name}'. "
                f"Registered: {list(cls._registry)}"
            )
        return cls._registry[name]

    @classmethod
    def list_agents(cls) -> list[dict]:
        """Return metadata list of all registered agents."""
        return [
            {"name": cls_obj.name, "description": cls_obj.description}
            for cls_obj in cls._registry.values()
        ]

    @classmethod
    def instantiate(cls, name: str) -> BaseAgent:
        """Instantiate and return an agent by name."""
        agent_class = cls.get(name)
        return agent_class()
