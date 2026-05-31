"""Tool registry — maps tools to agent roles via ``ToolRegistry``.

How to add a new tool:
1. Create the tool function in the appropriate subpackage.
2. Call ``tool_registry.register(my_tool, agent_roles=["profiler", "cleaner"])`` here.
   OR import the tool and add it to the existing ``register()`` calls below.
"""
from app.tools.data.eda import perform_eda
from app.agents.roles import AgentRole
class ToolRegistry:
    def __init__(self) -> None:
        self._by_role: dict[str, list] = {}
        self._all: dict[str, object] = {}

    # Registration
    def register(self, tool, *, agent_roles: list[str]) -> None:
        """Register a tool for one or more agent roles.

        Args:
            tool: A LangChain tool (decorated with ``@tool``).
            agent_roles: List of agent role names that may use this tool.
        """
        self._all[tool.name] = tool
        for role in agent_roles:
            self._by_role.setdefault(role, [])
            if tool not in self._by_role[role]:
                self._by_role[role].append(tool)

    # Lookup

    def get_tools(self, agent_role: str) -> list:
        """Return the list of tools registered for ``agent_role``.

        Returns an empty list (not an error) if the role has no tools.
        """
        return list(self._by_role.get(agent_role, []))

    def all_tools(self) -> list:
        """Return a deduplicated list of every registered tool."""
        return list(self._all.values())


# Module-level singleton
tool_registry = ToolRegistry()

# Register tools
## tool_registry.register(perform_eda,     agent_roles=["profiler"])
## tool_registry.register(save_to_file,    agent_roles=["reporter"])

# Backward-compatible constants
PROFILER_TOOLS    = tool_registry.get_tools("profiler")
VALIDATOR_TOOLS   = tool_registry.get_tools("validator")
REPORTER_TOOLS    = tool_registry.get_tools("reporter")
ALL_TOOLS         = tool_registry.all_tools()
