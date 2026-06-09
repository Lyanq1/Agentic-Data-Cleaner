"""Aggregate all v1 routers."""
from fastapi import APIRouter
from app.api.v1 import deduplication, health, pipeline, websocket

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(health.router, tags=["Health"])
v1_router.include_router(pipeline.router, tags=["Pipeline"])
v1_router.include_router(deduplication.router, tags=["Deduplication"])
v1_router.include_router(websocket.router, tags=["WebSocket"])
