"""Email normalization helpers."""

from __future__ import annotations


def normalize_email(value: object) -> str | None:
    """Normalize email values for comparison."""

    if value is None:
        return None
    text = str(value).strip().lower()
    if not text or text == "nan":
        return None
    return text
