"""Aggregate all v1 routers."""
from fastapi import APIRouter
from app.api.v1 import health

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(health.router, tags=["Health"])
