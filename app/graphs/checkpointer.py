"""LangGraph Postgres checkpointer setup for state persistence.

Uses `langgraph-checkpoint-postgres` to store graph snapshots in Postgres,
enabling HITL resume, fault tolerance, and long-running workflows.
"""
from contextlib import asynccontextmanager
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_checkpointer: AsyncPostgresSaver | None = None


@asynccontextmanager
async def get_checkpointer():
    """Context manager yielding an AsyncPostgresSaver instance.

    Usage:
        async with get_checkpointer() as cp:
            graph = builder.compile(checkpointer=cp)
    """
    settings = get_settings()
    # AsyncPostgresSaver expects a raw psycopg connection string
    conn_str = settings.postgres_url.replace("+asyncpg", "")
    async with AsyncPostgresSaver.from_conn_string(conn_str) as checkpointer:
        # Create checkpointing tables if they don't exist
        await checkpointer.setup()
        logger.info("LangGraph checkpointer ready", backend="postgres")
        yield checkpointer
