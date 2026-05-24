"""Job ORM model — tracks every agent run."""
import uuid
from sqlalchemy import JSON, String, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.models.db.base import Base, TimestampMixin
from app.core.constants import JobStatus

class Job(Base, TimestampMixin):
    """Represents a single agent pipeline run."""
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus), default=JobStatus.PENDING, nullable=False
    )
    input_file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    output_file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # LangGraph thread_id for checkpointer
    thread_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # Metadata & results stored as JSON
    job_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # HITL: which node is waiting
    hitl_waiting_node: Mapped[str | None] = mapped_column(String(128), nullable=True)
