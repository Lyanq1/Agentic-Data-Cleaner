"""GraphService — invoke, stream, and resume the LangGraph pipeline."""
from typing import AsyncGenerator
from app.graphs.builder import build_graph
from app.graphs.checkpointer import get_checkpointer
from app.graphs.states.graph_state import AgentState
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class GraphService:
    """Bridge between the FastAPI layer and LangGraph graph."""

    def _make_config(self, thread_id: str) -> dict:
        """Build the LangGraph run config for a given job/thread."""
        settings = get_settings()
        return {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": settings.graph_recursion_limit,
        }

    async def invoke(
        self,
        job_id: str,
        file_path: str,
        rules: dict,
    ) -> AgentState:
        """Run the graph to completion (or until first interrupt) and return final state.

        Args:
            job_id: Used as the LangGraph thread_id for checkpointing.
            file_path: Path to the input data file.
            rules: Cleaning rules / config dict.

        Returns:
            Final AgentState after graph terminates or pauses at interrupt.
        """
        initial_state: AgentState = {
            "job_id": job_id,
            "file_path": file_path,
            "rules": rules,
            "messages": [],
            "next_agent": "",
            "profile_result": None,
            "clean_result": None,
            "validation_result": None,
            "transform_result": None,
            "report_result": None,
            "human_approved": False,
            "human_feedback": "",
            "waiting_for_human": False,
            "hitl_node": None,
            "error": None,
            "retry_count": 0,
        }
        async with get_checkpointer() as checkpointer:
            graph = build_graph(checkpointer=checkpointer)
            config = self._make_config(job_id)
            final_state = await graph.ainvoke(initial_state, config=config)
        return final_state

    async def stream(
        self,
        job_id: str,
        file_path: str,
        rules: dict,
    ) -> AsyncGenerator[dict, None]:
        """Stream graph execution events as they happen.

        Yields:
            Dicts with event type and data for SSE consumption.
        """
        initial_state: AgentState = {
            "job_id": job_id,
            "file_path": file_path,
            "rules": rules,
            "messages": [],
            "next_agent": "",
            "profile_result": None,
            "clean_result": None,
            "validation_result": None,
            "transform_result": None,
            "report_result": None,
            "human_approved": False,
            "human_feedback": "",
            "waiting_for_human": False,
            "hitl_node": None,
            "error": None,
            "retry_count": 0,
        }
        async with get_checkpointer() as checkpointer:
            graph = build_graph(checkpointer=checkpointer)
            config = self._make_config(job_id)
            async for event in graph.astream(initial_state, config=config, stream_mode="updates"):
                yield {"type": "state_update", "data": event}

    async def resume(
        self,
        job_id: str,
        approved: bool,
        feedback: str = "",
    ) -> AgentState:
        """Resume a graph that is paused at an interrupt (HITL).

        Args:
            job_id: LangGraph thread_id.
            approved: True to continue, False to reject.
            feedback: Optional human feedback text.

        Returns:
            Updated AgentState after resume.
        """
        async with get_checkpointer() as checkpointer:
            graph = build_graph(checkpointer=checkpointer)
            config = self._make_config(job_id)
            # Supply the human response to the waiting interrupt()
            resume_payload = {"approved": approved, "feedback": feedback}
            final_state = await graph.ainvoke(
                input=None,  # None = resume from checkpoint
                config=config,
                command={"resume": resume_payload},
            )
        return final_state
