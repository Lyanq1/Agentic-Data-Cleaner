"""Column role inference for dedup normalization and fuzzy blocking."""

from __future__ import annotations

from typing import Literal

from app.graphs.states.profiles import ColumnSemanticProfileDetail, SemanticProfile

ColumnRole = Literal["phone", "email", "address", "company_name", "person_name"]
VALID_COLUMN_ROLES: set[str] = {"phone", "email", "address", "company_name", "person_name"}


def infer_column_role(
    column_name: str,
    *,
    explicit_roles: dict[str, str] | None = None,
    semantic_profile: SemanticProfile | None = None,
) -> ColumnRole | None:
    """Infer the semantic role of a column for dedup operations.

    The primary source of truth is the LLM-selected role plan. Semantic-profile
    metadata is a conservative fallback. Column-name keyword matching is
    intentionally not used here because it does not generalize safely across
    datasets.
    """

    if explicit_roles:
        explicit_role = explicit_roles.get(column_name)
        if explicit_role in VALID_COLUMN_ROLES:
            return explicit_role  # type: ignore[return-value]

    detail = semantic_profile.columns.get(column_name) if semantic_profile else None
    if detail is None:
        return None
    return _infer_from_semantic_detail(detail)


def _infer_from_semantic_detail(detail: ColumnSemanticProfileDetail) -> ColumnRole | None:
    logical_group = detail.logical_group.casefold().strip()
    description = detail.description.casefold().strip()
    allow_missing_reason = detail.allow_missing_reason.casefold().strip()
    expected_type_reason = detail.expected_type_reason.casefold().strip()
    potential_dmv_reason = detail.potential_dmv_reason.casefold().strip()
    error_reason = (detail.error_reason or "").casefold().strip()
    expected_pattern = (detail.expected_str_pattern or "").casefold().strip()
    expected_pattern_reason = (detail.expected_str_pattern_reason or "").casefold().strip()

    evidence = " ".join(
        part
        for part in [
            logical_group,
            description,
            allow_missing_reason,
            expected_type_reason,
            potential_dmv_reason,
            error_reason,
            expected_pattern,
            expected_pattern_reason,
        ]
        if part
    )

    if _semantic_mentions_email(evidence, expected_pattern):
        return "email"
    if _semantic_mentions_phone(evidence, expected_pattern):
        return "phone"
    if logical_group in {"location", "address"}:
        return "address"
    if logical_group in {"organization", "company", "vendor", "provider", "agency", "site"}:
        return "company_name"
    if logical_group in {"person", "contact", "customer", "identity"} and "identifier" not in evidence:
        return "person_name"
    if _semantic_mentions_address(evidence):
        return "address"
    if _semantic_mentions_company(evidence):
        return "company_name"
    if _semantic_mentions_person(evidence):
        return "person_name"
    return None


def _semantic_mentions_email(evidence: str, expected_pattern: str) -> bool:
    return "email" in evidence or "e-mail" in evidence or "@" in expected_pattern


def _semantic_mentions_phone(evidence: str, expected_pattern: str) -> bool:
    return (
        "phone" in evidence
        or "telephone" in evidence
        or "mobile" in evidence
        or "contact number" in evidence
        or "\\d" in expected_pattern and "{" in expected_pattern and "}" in expected_pattern
    )


def _semantic_mentions_address(evidence: str) -> bool:
    return any(
        marker in evidence
        for marker in ["address", "postal", "street", "city", "district", "ward", "zip", "location"]
    )


def _semantic_mentions_company(evidence: str) -> bool:
    return any(
        marker in evidence
        for marker in ["company", "organization", "business", "agency", "provider", "vendor", "site"]
    )


def _semantic_mentions_person(evidence: str) -> bool:
    return any(
        marker in evidence
        for marker in ["person", "contact", "director", "customer name", "full name", "individual"]
    )
