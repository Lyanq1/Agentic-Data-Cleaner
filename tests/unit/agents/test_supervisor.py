"""Unit tests for SupervisorAgent with mocked LLM."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_supervisor_routes_to_profiler(mocker):
    """Supervisor should return next_agent='profiler_node' when no profile yet."""
    mock_response = MagicMock()
    mock_response.content = json.dumps({"next_agent": "profiler_node", "reasoning": "No profile yet"})
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)
    mocker.patch("app.core.llm_factory.create_llm", return_value=mock_llm)

    from app.agents.supervisor.agent import SupervisorAgent
    agent = SupervisorAgent()
    state = {
        "job_id": "test-job",
        "file_path": "/tmp/data.csv",
        "rules": {},
        "messages": [],
        "profile_result": None,
        "clean_result": None,
        "validation_result": None,
        "transform_result": None,
        "report_result": None,
        "next_agent": "",
        "human_approved": False,
        "human_feedback": "",
        "waiting_for_human": False,
        "hitl_node": None,
        "error": None,
        "retry_count": 0,
    }
    output = await agent.run(state)
    assert output.success is True
    assert output.next_agent == "profiler_node"
