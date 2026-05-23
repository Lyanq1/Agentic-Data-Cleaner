"""JobService — CRUD operations and status tracking for Jobs."""
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.db.job import Job, JobStatus
from app.models.schemas.job import JobCreate
from app.core.logging import get_logger

logger = get_logger(__name__)


class JobService:
    """Manages Job lifecycle: create, read, update status."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_job(self, payload: JobCreate) -> Job:
        """Persist a new Job record and return it."""
        job = Job(
            id=str(uuid.uuid4()),
            status=JobStatus.PENDING,
            input_file_path=payload.file_path,
            job_metadata=payload.metadata,
        )
        self.session.add(job)
        await self.session.flush()
        logger.info("Job created", job_id=job.id)
        return job

    async def get_job(self, job_id: str) -> Job | None:
        """Fetch a job by ID."""
        result = await self.session.execute(select(Job).where(Job.id == job_id))
        return result.scalar_one_or_none()

    async def update_status(
        self,
        job_id: str,
        status: JobStatus,
        *,
        error_message: str | None = None,
        result: dict | None = None,
        hitl_waiting_node: str | None = None,
        thread_id: str | None = None,
    ) -> Job | None:
        """Update job status and optional fields."""
        job = await self.get_job(job_id)
        if job is None:
            logger.warning("Job not found for status update", job_id=job_id)
            return None
        job.status = status
        if error_message is not None:
            job.error_message = error_message
        if result is not None:
            job.result = result
        if hitl_waiting_node is not None:
            job.hitl_waiting_node = hitl_waiting_node
        if thread_id is not None:
            job.thread_id = thread_id
        await self.session.flush()
        logger.info("Job status updated", job_id=job_id, status=status)
        return job

    async def list_jobs(self, page: int = 1, page_size: int = 20) -> tuple[list[Job], int]:
        """Paginated list of jobs."""
        offset = (page - 1) * page_size
        result = await self.session.execute(
            select(Job).order_by(Job.created_at.desc()).offset(offset).limit(page_size)
        )
        jobs = list(result.scalars().all())
        count_result = await self.session.execute(select(Job))
        total = len(list(count_result.scalars().all()))  # TODO: use COUNT query
        return jobs, total
