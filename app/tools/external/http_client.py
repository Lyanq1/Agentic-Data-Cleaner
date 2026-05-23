"""Tool: call an external REST API endpoint.

This is a placeholder/skeleton for integrating external data services.
Customize the tool arguments and response parsing for your use case.
"""
import httpx
from langchain_core.tools import tool
from app.core.logging import get_logger

logger = get_logger(__name__)


@tool
async def call_external_api(
    url: str,
    method: str = "GET",
    payload: dict | None = None,
    headers: dict | None = None,
    timeout: float = 30.0,
) -> dict:
    """Call an external REST API and return the JSON response.

    Args:
        url: Full URL of the endpoint.
        method: HTTP method — "GET" | "POST" | "PUT" | "PATCH" | "DELETE".
        payload: Request body as dict (for POST/PUT).
        headers: Additional HTTP headers.
        timeout: Request timeout in seconds.

    Returns:
        dict with status_code and response_body.

    TODO:
        - Add authentication (Bearer token, API key header)
        - Add retry logic with tenacity
        - Add response schema validation
    """
    # TODO: configure auth from Settings
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(
            method=method.upper(),
            url=url,
            json=payload,
            headers=headers or {},
        )
    logger.info("External API call", url=url, method=method, status=response.status_code)
    return {
        "status_code": response.status_code,
        "response_body": response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text,
    }
