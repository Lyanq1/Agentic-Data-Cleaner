"""Phone normalization helpers."""

from __future__ import annotations

import re


def normalize_phone(value: object) -> str | None:
    """Normalize phone-like values for comparison across datasets.

    The output is a stable digits-only canonical representation.
    This function is intentionally generic. It does not hardcode country-specific
    prefixes or numbering plans.
    """

    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None

    text = re.sub(r"(ext|extension|x)\s*\d+$", "", text, flags=re.IGNORECASE).strip()
    if text.startswith("00"):
        text = text[2:]

    digits = re.sub(r"\D+", "", text)
    if not digits:
        return None
    if not 7 <= len(digits) <= 15:
        return None
    return digits
