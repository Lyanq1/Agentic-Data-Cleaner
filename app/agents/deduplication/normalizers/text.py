"""Shared text normalization helpers for fuzzy blocking."""

from __future__ import annotations

import unicodedata


def normalize_text(value: object, *, field_type: str | None = None) -> str:
    """Normalize free text for blocking and similarity scoring.

    This is intentionally dataset-agnostic. It does not try to infer semantics
    from column names or locale-specific stopword lists; it only performs
    Unicode-safe canonicalization so fuzzy scoring works consistently across
    datasets.
    """

    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.casefold() == "nan":
        return ""

    decomposed = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", text).casefold())
    normalized_chars: list[str] = []
    last_was_space = False
    for char in decomposed:
        if unicodedata.combining(char):
            continue

        category = unicodedata.category(char)
        if category[0] in {"L", "N"}:
            normalized_chars.append(char)
            last_was_space = False
            continue

        if not last_was_space:
            normalized_chars.append(" ")
            last_was_space = True

    return "".join(normalized_chars).strip()


def tokenize_text(value: object, *, field_type: str | None = None) -> list[str]:
    normalized = normalize_text(value, field_type=field_type)
    return normalized.split() if normalized else []


def shingle_text(value: object, *, size: int, field_type: str | None = None) -> set[str]:
    normalized = normalize_text(value, field_type=field_type)
    if not normalized:
        return set()
    if size <= 1:
        return set(normalized.split())
    if " " in normalized and field_type == "address":
        tokens = normalized.split()
        if len(tokens) < size:
            return {" ".join(tokens)}
        return {" ".join(tokens[index : index + size]) for index in range(len(tokens) - size + 1)}
    compact = normalized.replace(" ", "")
    if len(compact) < size:
        return {compact}
    return {compact[index : index + size] for index in range(len(compact) - size + 1)}


def is_cross_script_pair(left: object, right: object) -> bool:
    """Return True when two text values look like the same field rendered in different scripts."""

    left_text = str(left or "").strip()
    right_text = str(right or "").strip()
    if not left_text or not right_text:
        return False

    def _char_sets(text: str) -> tuple[bool, bool]:
        has_latin = False
        has_non_latin = False
        for char in text:
            if not char.isalpha():
                continue
            name = unicodedata.name(char, "")
            if "LATIN" in name:
                has_latin = True
            else:
                has_non_latin = True
        return has_latin, has_non_latin

    left_latin, left_non_latin = _char_sets(left_text)
    right_latin, right_non_latin = _char_sets(right_text)
    return (left_latin and right_non_latin) or (right_latin and left_non_latin)
