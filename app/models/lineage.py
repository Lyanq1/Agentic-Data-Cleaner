import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class Session(Base):
    __tablename__ = "sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    versions = relationship("LineageVersion", back_populates="session", cascade="all, delete-orphan")
    records = relationship("DatasetRecord", back_populates="session", cascade="all, delete-orphan")


class LineageVersion(Base):
    __tablename__ = "lineage_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    version = Column(Integer, nullable=False)
    agent_name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    session = relationship("Session", back_populates="versions")

    __table_args__ = (
        Index("ix_lineage_versions_session_version", "session_id", "version", unique=True),
    )


class DatasetRecord(Base):
    """Stores the actual data rows in JSONB format."""
    __tablename__ = "dataset_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    version = Column(Integer, nullable=False)
    data = Column(JSONB, nullable=False)
    
    # Optional: store original row index to trace specific rows
    row_index = Column(Integer, nullable=True)

    session = relationship("Session", back_populates="records")

    __table_args__ = (
        Index("ix_dataset_records_session_version", "session_id", "version"),
    )
