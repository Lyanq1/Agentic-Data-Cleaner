"""FastAPI shared dependencies — injected via Depends()."""
from fastapi import Depends
from app.core.redis_client import get_redis

# You can add FastAPI dependencies here as needed
