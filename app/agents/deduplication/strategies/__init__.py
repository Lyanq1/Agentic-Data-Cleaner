"""Deterministic deduplication strategies."""

from app.agents.deduplication.strategies.composite_key import (
    CompositeKeyExecutionResult,
    ExactKeyDedupConfig,
    build_normalized_key_frame,
    execute_exact_key_dedup,
    has_normalized_key_duplicates,
)
from app.agents.deduplication.strategies.full_row import execute_full_row_dedup
from app.agents.deduplication.strategies.fuzzy_blocking import run_fuzzy_blocking

__all__ = [
    "CompositeKeyExecutionResult",
    "ExactKeyDedupConfig",
    "build_normalized_key_frame",
    "execute_exact_key_dedup",
    "execute_full_row_dedup",
    "has_normalized_key_duplicates",
    "run_fuzzy_blocking",
]
