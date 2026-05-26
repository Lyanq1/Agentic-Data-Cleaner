"""FastAPI application factory with lifespan context manager."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.config import get_settings
from app.core.database import close_engine
from app.core.redis_client import close_redis
from app.api.middleware import register_middleware
from app.api.v1.router import v1_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown hooks."""
    # ── Startup ──
    settings = get_settings()
    # TODO: run Alembic migrations on startup (optional)
    # TODO: warm up LLM connection pool
    yield
    # ── Shutdown ──
    await close_engine()
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


# Module-level app instance for uvicorn
app = create_app()
