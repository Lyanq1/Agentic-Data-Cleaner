"""Normalization helpers for deduplication comparisons."""

from app.agents.deduplication.normalizers.email import normalize_email
from app.agents.deduplication.normalizers.phone import normalize_phone
from app.agents.deduplication.normalizers.text import (
    is_cross_script_pair,
    normalize_text,
    shingle_text,
    tokenize_text,
)

__all__ = [
    "is_cross_script_pair",
    "normalize_email",
    "normalize_phone",
    "normalize_text",
    "shingle_text",
    "tokenize_text",
]
