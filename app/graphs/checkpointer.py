"""LangGraph Postgres checkpointer, managed by ``CheckpointerManager``.

Uses ``langgraph-checkpoint-postgres`` to store graph snapshots in Postgres,
enabling HITL resume, fault tolerance, and long-running workflows.
"""
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from app.config.config import get_settings

class CheckpointerManager:
    """Manages the lifecycle of the LangGraph Postgres checkpointer.

    Use the module-level ``get_checkpointer_manager()`` to obtain the singleton.

    Example::

        async with get_checkpointer_manager().get() as cp:
            graph = builder.compile(checkpointer=cp)
    """

    @asynccontextmanager
    async def get(self) -> AsyncIterator[AsyncPostgresSaver]:
        """Async context manager yielding a ready ``AsyncPostgresSaver``.

        Creates the checkpointing tables on first use if they don't exist.
        """
        settings = get_settings()
        # AsyncPostgresSaver expects a raw psycopg connection string
        conn_str = settings.postgres_url
        async with AsyncPostgresSaver.from_conn_string(conn_str) as checkpointer:
            await checkpointer.setup()
            yield checkpointer


# Module-level singleton
_checkpointer_manager: CheckpointerManager | None = None
def get_checkpointer_manager() -> CheckpointerManager:
    """Return the cached ``CheckpointerManager`` singleton."""
    global _checkpointer_manager
    if _checkpointer_manager is None:
        _checkpointer_manager = CheckpointerManager()
    return _checkpointer_manager

# Backward-compatible shim
@asynccontextmanager
async def get_checkpointer() -> AsyncIterator[AsyncPostgresSaver]:
    """Backward-compatible shim — prefer ``get_checkpointer_manager().get()``."""
    async with get_checkpointer_manager().get() as cp:
        yield cp

