"""Template Agent — copy and customize to create a new agent.

DO NOT register this template agent (it is not in AgentRegistry by default).

How to create a new agent
--------------------------
1. Copy this directory (``_template/``) to a new folder under ``app/agents/``.
2. Rename the class, set ``name``, ``description``, and ``tools``.
3. Implement ``run()``.
4. Add ``@AgentRegistry.auto_register`` to register it.
5. Register your tools in ``app/tools/registry.py``.
"""
from app.agents.base import BaseAgent
from app.graphs.states.graph_state import AgentState


class TemplateAgent(BaseAgent):
    """TODO: Replace this docstring with a description of your agent."""

    name = "template_agent"  # TODO: rename — must be unique
    description = "TODO: describe what this agent does"  # used by Supervisor

    # Declare your tools here — they will be bound to the LLM automatically.
    # from app.tools.registry import YOUR_AGENT_TOOLS
    # tools = YOUR_AGENT_TOOLS
    tools = []  # leave empty for a plain LLM agent (no tools)

    async def run(self, state: AgentState) -> AgentOutput:
        """TODO: implement your agent logic here.

        Args:
            state: Current AgentState snapshot.

        Returns:
            AgentOutput with results. Set next_agent to route directly,
            or leave None to let the supervisor decide.
        """
        # TODO: implement tool-calling loop using self.llm
        return AgentOutput(
            agent_name=self.name,
            success=True,
            data={"status": "TODO: implement"},
            next_agent=None,  # let supervisor decide
        )
