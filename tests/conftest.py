"""Pytest fixtures shared across all tests."""
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import create_app
from app.core.config import get_settings


@pytest.fixture(scope="session")
def settings():
    """Return app settings (reads from .env.test if present)."""
    return get_settings()


@pytest.fixture
async def client():
    """Async HTTP test client for the FastAPI app."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_llm(mocker):
    """Mock the LLM factory to avoid real API calls in unit tests."""
    from unittest.mock import AsyncMock, MagicMock
    mock = MagicMock()
    mock.ainvoke = AsyncMock(return_value=MagicMock(content='{"next_agent": "FINISH", "reasoning": "test"}}'))
    mocker.patch("app.core.llm_factory.create_llm", return_value=mock)
    return mock
