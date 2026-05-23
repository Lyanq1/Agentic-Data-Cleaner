"""FastAPI shared dependencies — injected via Depends()."""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db_session
from app.services.job_service import JobService
from app.services.graph_service import GraphService
from app.services.file_service import FileService


async def get_job_service(session: AsyncSession = Depends(get_db_session)) -> JobService:
    """Inject JobService with an active DB session."""
    return JobService(session)


async def get_graph_service() -> GraphService:
    """Inject GraphService."""
    return GraphService()


async def get_file_service() -> FileService:
    """Inject FileService."""
    return FileService()
