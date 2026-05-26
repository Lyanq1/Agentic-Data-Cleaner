"""Async SQLAlchemy engine and session factory, managed by DatabaseManager."""
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.core.config import get_settings


class DatabaseManager:
    """Owns the SQLAlchemy async engine and session factory lifecycle.

    Use the module-level ``get_database_manager()`` to obtain the singleton.

    Example::

        db = get_database_manager()
        async for session in db.get_session():
            ...
    """

    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    # ── Engine ────────────────────────────────────────────────────────────────

    def get_engine(self) -> AsyncEngine:
        """Return (and lazily create) the async SQLAlchemy engine."""
        if self._engine is None:
            settings = get_settings()
            url = settings.postgres_url
            if url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            self._engine = create_async_engine(
                url,
                pool_size=settings.postgres_pool_size,
                max_overflow=settings.postgres_max_overflow,
                echo=settings.debug,
            )
        return self._engine

    # ── Session factory ───────────────────────────────────────────────────────

    def get_session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Return (and lazily create) the async session factory."""
        if self._session_factory is None:
            self._session_factory = async_sessionmaker(
                bind=self.get_engine(),
                expire_on_commit=False,
                class_=AsyncSession,
            )
        return self._session_factory

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield an ``AsyncSession`` with automatic commit/rollback."""
        factory = self.get_session_factory()
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Dispose the engine on application shutdown."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None


# ── Module-level singleton ────────────────────────────────────────────────────

_db_manager: DatabaseManager | None = None


def get_database_manager() -> DatabaseManager:
    """Return the cached ``DatabaseManager`` singleton."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


# ── Backward-compatible helpers used by FastAPI Depends() ────────────────────

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an ``AsyncSession`` per request."""
    async for session in get_database_manager().get_session():
        yield session


async def close_engine() -> None:
    """Dispose the engine on app shutdown (delegates to DatabaseManager)."""
    await get_database_manager().close()

