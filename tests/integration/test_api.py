"""Integration tests for FastAPI endpoints."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    """GET /health should return 200."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_create_job_returns_202(client: AsyncClient, mocker):
    """POST /api/v1/jobs should return 202 and a job_id."""
    # TODO: mock DB and graph service for isolated test
    pass  # Implement after DB fixtures are set up
