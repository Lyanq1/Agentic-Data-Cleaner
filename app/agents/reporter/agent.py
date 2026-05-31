"""Reporter Agent — compiles and saves the final pipeline report."""
from app.agents.base import BaseAgent
from app.agents.registry import AgentRegistry
from app.agents.reporter.prompts import REPORTER_SYSTEM_PROMPT
from app.graphs.states.global_state import AgentState
from app.tools.tool_registration import REPORTER_TOOLS
from app.agents.base import AgentOutput

@AgentRegistry.auto_register
class ReporterAgent(BaseAgent):
    """Generates the final pipeline report and persists it to disk.

    Aggregates the results from all previous pipeline stages (profiling,
    cleaning, validation, transformation) into a structured, human-readable
    report saved via the save_to_file tool.
    """

    name = "reporter"
    description = "Generates and saves the final data quality report summarising all pipeline stages"
    tools = REPORTER_TOOLS

    async def run(self, state: AgentState) -> AgentOutput:
        """Compile results from all stages and save the final report.

        TODO: Implement full ReAct tool-calling loop.
        """
        # TODO: Replace with full LangChain agent executor / ReAct loop
        return AgentOutput(
            agent_name=self.name,
            success=True,
            data={"status": "TODO: implement reporting logic"},
        )
