"""Typer CLI entry point for the `ade` command."""
import typer
import uvicorn
from app.core.config import get_settings

app = typer.Typer(
    name="ade",
    help="Agentic Data Cleaner — CLI interface",
    add_completion=False,
)


@app.command("serve")
def serve(
    host: str = typer.Option(None, help="Host to bind"),
    port: int = typer.Option(None, help="Port to bind"),
    reload: bool = typer.Option(False, help="Enable auto-reload (dev only)"),
) -> None:
    """Start the FastAPI server."""
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=host or settings.api_host,
        port=port or settings.api_port,
        reload=reload,
        log_level="debug" if settings.debug else "info",
    )


@app.command("run-job")
def run_job(
    file_path: str = typer.Argument(..., help="Path to input data file"),
    rules: str = typer.Option("{}", help="JSON string of cleaning rules"),
) -> None:
    """Trigger a data cleaning job from the CLI (without API server)."""
    import asyncio
    import json
    from app.services.graph.graph_service import GraphService

    async def _run():
        import uuid
        job_id = str(uuid.uuid4())
        graph_svc = GraphService()
        typer.echo(f"Starting job {job_id} for file: {file_path}")
        result = await graph_svc.invoke(job_id, file_path, json.loads(rules))
        typer.echo(f"Job completed. Final state keys: {list(result.keys())}")

    asyncio.run(_run())


@app.command("list-agents")
def list_agents() -> None:
    """List all registered agents."""
    from app.agents.registry import AgentRegistry
    import app.agents.supervisor  # noqa: F401 — trigger registration
    import app.agents.profiler    # noqa: F401
    import app.agents.cleaner     # noqa: F401
    import app.agents.validator   # noqa: F401
    import app.agents.transformer # noqa: F401
    import app.agents.reporter    # noqa: F401
    agents = AgentRegistry.list_agents()
    for a in agents:
        typer.echo(f"  • {a['name']}: {a['description']}")


if __name__ == "__main__":
    app()
