"""Aggregate all v1 routers."""
from fastapi import APIRouter
from app.api.v1 import jobs, hitl, streams, health

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(health.router, tags=["Health"])
v1_router.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])
v1_router.include_router(hitl.router, prefix="/jobs", tags=["HITL"])
v1_router.include_router(streams.router, prefix="/jobs", tags=["Streaming"])
