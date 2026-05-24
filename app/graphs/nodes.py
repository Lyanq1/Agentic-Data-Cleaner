"""Node wrapper functions — thin adapters between LangGraph and agent classes.

Each node function:
1. Extracts relevant fields from AgentState
2. Calls the corresponding agent's .run() method
3. Returns a state delta dict (partial update)
"""
from langgraph.types import interrupt
from app.graphs.states.graph_state import AgentState
from app.core.logging import get_logger

logger = get_logger(__name__)


async def supervisor_node(state: AgentState) -> dict:
    """Supervisor node — decides which worker agent runs next."""
    from app.agents.supervisor.agent import SupervisorAgent
    agent = SupervisorAgent()
    result = await agent.run(state)
    return {"next_agent": result.next_agent, "messages": result.data.get("messages", [])}


async def profiler_node(state: AgentState) -> dict:
    """Data Profiler node."""
    from app.agents.profiler.agent import ProfilerAgent
    agent = ProfilerAgent()
    result = await agent.run(state)
    return {"profile_result": result.data, "error": result.error}


async def cleaner_node(state: AgentState) -> dict:
    """Data Cleaner node — includes HITL interrupt before execution."""
    # ── HITL: pause here and wait for human approval ──
    human_response = interrupt(
        value={
            "message": "Cleaner agent is about to modify your data. Please review the profile result and approve.",
            "profile_result": state.get("profile_result"),
            "rules": state.get("rules"),
        }
    )
    # Resume: human_response contains the approved/feedback payload
    if not human_response.get("approved", False):
        return {"error": "User rejected cleaning step.", "next_agent": None}

    from app.agents.cleaner.agent import CleanerAgent
    agent = CleanerAgent()
    result = await agent.run(state)
    return {"clean_result": result.data, "error": result.error}


async def validator_node(state: AgentState) -> dict:
    """Data Validator node."""
    from app.agents.validator.agent import ValidatorAgent
    agent = ValidatorAgent()
    result = await agent.run(state)
    return {"validation_result": result.data, "error": result.error}


async def transformer_node(state: AgentState) -> dict:
    """Data Transformer node — includes HITL interrupt before execution."""
    human_response = interrupt(
        value={
            "message": "Transformer agent is about to apply transformations. Please approve.",
            "validation_result": state.get("validation_result"),
        }
    )
    if not human_response.get("approved", False):
        return {"error": "User rejected transformation step.", "next_agent": None}

    from app.agents.transformer.agent import TransformerAgent
    agent = TransformerAgent()
    result = await agent.run(state)
    return {"transform_result": result.data, "error": result.error}


async def reporter_node(state: AgentState) -> dict:
    """Reporter node — generates final report."""
    from app.agents.reporter.agent import ReporterAgent
    agent = ReporterAgent()
    result = await agent.run(state)
    return {"report_result": result.data, "error": result.error}


async def error_node(state: AgentState) -> dict:
    """Error handler node — logs and returns final error state."""
    logger.error("Graph terminated due to error", error=state.get("error"), job_id=state.get("job_id"))
    return {"next_agent": None}
