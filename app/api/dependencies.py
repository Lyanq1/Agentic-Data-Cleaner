"""FastAPI shared dependencies — injected via Depends()."""
from fastapi import Depends
from app.core.redis_client import get_redis
