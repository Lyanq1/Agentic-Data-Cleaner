"""Seed script — populate the database with sample data for development."""
import asyncio
from app.core.database import get_session_factory
from app.models.db.job import Job, JobStatus


async def seed():
    factory = get_session_factory()
    async with factory() as session:
        sample_job = Job(
            id="seed-job-001",
            status=JobStatus.COMPLETED,
            input_file_path="data/uploads/sample.csv",
            job_metadata={"source": "seed"},
        )
        session.add(sample_job)
        await session.commit()
        print("Seeded 1 sample job.")


if __name__ == "__main__":
    asyncio.run(seed())
