"""FastAPI shared dependencies — injected via Depends()."""
from collections.abc import AsyncGenerator
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_database_manager


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session per request via ``DatabaseManager``."""
    async for session in get_database_manager().get_session():
        yield session
