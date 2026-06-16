"""FastAPI application factory with lifespan context manager."""
import asyncio
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from app.config.config import get_settings
from app.core.redis_client import close_redis, get_redis
from app.api.middleware import register_middleware
from app.api.v1.router import v1_router
from app.services.pipeline import get_pipeline_state

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown hooks."""

    # Startup
    settings = get_settings()
    redis_client = get_redis()
    yield

    # Shutdown
    await close_redis()

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Multi-Agent ETL System for Structured Data Cleaning using LangGraph",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    register_middleware(app)    
    app.include_router(v1_router)
    return app

app = create_app()


def _state_status(state: dict) -> str:
    next_nodes = state.get("next_node") or []
    if isinstance(next_nodes, str):
        next_nodes = [next_nodes]
    graph_at_end = len(next_nodes) == 0 or "__end__" in next_nodes
    completed_steps = state.get("completed_steps") or []
    report_completed = state.get("current_step") == "reporting" or "reporting" in completed_steps
    if graph_at_end and report_completed:
        return "completed"
    if graph_at_end and state.get("errors"):
        return "failed"
    return "running"


@app.websocket("/ws/{run_id}")
async def websocket_pipeline_logs(websocket: WebSocket, run_id: str):
    """Stream checkpointed pipeline logs to the frontend terminal."""
    await websocket.accept()
    sent_log_count = 0
    last_status: str | None = None

    try:
        while True:
            state = await get_pipeline_state(run_id)
            if state is None:
                await websocket.send_json(
                    {
                        "event": "log",
                        "log": {
                            "timestamp": time.time(),
                            "agent": "system",
                            "level": "warning",
                            "message": f"Run '{run_id}' not found yet.",
                        },
                    }
                )
                await asyncio.sleep(1)
                continue

            agent_logs_dict = state.get("agent_logs") or {}
            all_logs = []
            if isinstance(agent_logs_dict, dict):
                for task_data in agent_logs_dict.values():
                    if isinstance(task_data, dict) and "logs" in task_data:
                        if isinstance(task_data["logs"], list):
                            all_logs.extend(task_data["logs"])
                    elif isinstance(task_data, list):
                        all_logs.extend(task_data)
            elif isinstance(agent_logs_dict, list):
                all_logs = agent_logs_dict

            # Sort logs chronologically by timestamp
            all_logs.sort(key=lambda x: x.get("timestamp") or 0.0)

            for log in all_logs[sent_log_count:]:
                await websocket.send_json({"event": "log", "log": log})
            sent_log_count = len(all_logs)

            status = _state_status(state)
            if status != last_status:
                await websocket.send_json({"event": "status_change", "status": status})
                last_status = status

            if status in {"completed", "failed"}:
                await asyncio.sleep(0.5)
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return