"""Pydantic schemas for Job API endpoints."""
from datetime import datetime
from pydantic import BaseModel, Field
from app.models.db.job import JobStatus


class JobCreate(BaseModel):
    """Request body for creating a new job."""
    file_path: str = Field(..., description="Path to uploaded file (relative to upload_dir)")
    rules: dict = Field(default_factory=dict, description="Optional cleaning rules / config")
    metadata: dict = Field(default_factory=dict, description="Arbitrary job metadata")


class JobResponse(BaseModel):
    """Response schema for a job."""
    id: str
    status: JobStatus
    input_file_path: str | None
    output_file_path: str | None
    thread_id: str | None
    result: dict | None
    error_message: str | None
    hitl_waiting_node: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobResumeRequest(BaseModel):
    """Request body for HITL resume."""
    approved: bool = Field(..., description="True to approve and continue, False to reject")
    feedback: str = Field(default="", description="Optional human feedback injected into agent state")


class JobListResponse(BaseModel):
    """Paginated list of jobs."""
    items: list[JobResponse]
    total: int
    page: int
    page_size: int
