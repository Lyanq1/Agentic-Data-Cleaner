"""End-to-end graph tests (requires Postgres + Redis running)."""
import pytest


@pytest.mark.asyncio
@pytest.mark.integration  # Run only with: pytest -m integration
async def test_graph_runs_to_completion(mocker):
    """Graph should run from initial state to FINISH without error."""
    # TODO: mock all agent LLM calls, use in-memory checkpointer
    pass
