"""Flexible semantic descriptors with private deterministic intent resolvers."""

from __future__ import annotations

from app.agents.deduplication.models import ColumnSemanticDescriptor
from app.graphs.states.profiles import ColumnSemanticProfileDetail, SemanticProfile


def infer_column_semantics(
    column_name: str,
    *,
    explicit_semantics: dict[str, ColumnSemanticDescriptor] | None = None,
    semantic_profile: SemanticProfile | None = None,
) -> ColumnSemanticDescriptor | None:
    """Infer flexible semantic descriptors for a column.

    The LLM-facing contract is intentionally flexible. The deterministic runtime
    later resolves these descriptors into private execution handlers.
    """

    if explicit_semantics and column_name in explicit_semantics:
        return explicit_semantics[column_name]

    detail = semantic_profile.columns.get(column_name) if semantic_profile else None
    if detail is None:
        return None
    return _infer_from_semantic_detail(detail)


def resolve_normalization_handler(descriptor: ColumnSemanticDescriptor | None) -> str:
    if descriptor is None:
        return "text"

    intent_evidence = " ".join(
        [
            descriptor.normalization_intent,
            descriptor.identifier_intent,
            descriptor.comparison_intent,
            descriptor.semantic_label,
        ]
    ).casefold()
    if any(marker in intent_evidence for marker in ["phone", "telephone", "mobile", "contact number"]):
        return "phone"
    if any(marker in intent_evidence for marker in ["email", "e-mail", "mailbox"]):
        return "email"
    if any(marker in intent_evidence for marker in ["domain", "website", "url", "web"]):
        return "domain"
    if any(marker in intent_evidence for marker in ["identifier", "registration", "license", "tax", "provider id"]):
        return "identifier"
    return "text"


def resolve_name_family(descriptor: ColumnSemanticDescriptor | None) -> str:
    if descriptor is None:
        return "generic_text"

    intent_evidence = " ".join(
        [
            descriptor.comparison_intent,
            descriptor.blocking_intent,
            descriptor.semantic_label,
        ]
    ).casefold()
    if any(marker in intent_evidence for marker in ["organization", "company", "vendor", "provider", "facility", "school", "hospital", "clinic", "site"]):
        return "organization_name"
    if any(marker in intent_evidence for marker in ["person", "contact", "customer", "individual", "patient", "full name"]):
        return "person_name"
    if any(marker in intent_evidence for marker in ["address", "location", "street", "postal", "city", "district", "ward"]):
        return "address"
    return "generic_text"


def descriptor_is_hard_identifier(descriptor: ColumnSemanticDescriptor | None) -> bool:
    if descriptor is None:
        return False
    evidence = " ".join(
        [
            descriptor.identifier_intent,
            descriptor.normalization_intent,
            descriptor.comparison_intent,
            descriptor.semantic_label,
        ]
    ).casefold()
    return any(
        marker in evidence
        for marker in [
            "phone",
            "email",
            "registration identifier",
            "license identifier",
            "tax identifier",
            "provider identifier",
            "business identifier",
            "customer identifier",
        ]
    )


def descriptor_is_name_like(descriptor: ColumnSemanticDescriptor | None) -> bool:
    family = resolve_name_family(descriptor)
    return family in {"organization_name", "person_name"}


def _infer_from_semantic_detail(detail: ColumnSemanticProfileDetail) -> ColumnSemanticDescriptor | None:
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
        return ColumnSemanticDescriptor(
            semantic_label=detail.description or "email field",
            comparison_intent="email-like identifier",
            normalization_intent="email canonicalization",
            identifier_intent="contact identifier",
            blocking_intent="exact identifier matching",
        )
    if _semantic_mentions_phone(evidence, expected_pattern):
        return ColumnSemanticDescriptor(
            semantic_label=detail.description or "phone field",
            comparison_intent="phone-like identifier",
            normalization_intent="phone canonicalization",
            identifier_intent="contact identifier",
            blocking_intent="exact identifier matching",
        )
    if logical_group in {"location", "address"} or _semantic_mentions_address(evidence):
        return ColumnSemanticDescriptor(
            semantic_label=detail.description or "address field",
            comparison_intent="address-like location",
            normalization_intent="address text normalization",
            identifier_intent="supporting location context",
            blocking_intent="location-aware fuzzy blocking",
        )
    if logical_group in {"organization", "company", "vendor", "provider", "agency", "site"} or _semantic_mentions_company(evidence):
        return ColumnSemanticDescriptor(
            semantic_label=detail.description or "organization name",
            comparison_intent="organization-like entity name",
            normalization_intent="organization name normalization",
            identifier_intent="entity name context",
            blocking_intent="organization-name fuzzy blocking",
        )
    if logical_group in {"person", "contact", "customer", "identity"} and "identifier" not in evidence or _semantic_mentions_person(evidence):
        return ColumnSemanticDescriptor(
            semantic_label=detail.description or "person name",
            comparison_intent="person-like entity name",
            normalization_intent="person name normalization",
            identifier_intent="person identity context",
            blocking_intent="person-name fuzzy blocking",
        )
    if any(marker in evidence for marker in ["identifier", "registration", "license", "tax code", "provider id", "customer id"]):
        return ColumnSemanticDescriptor(
            semantic_label=detail.description or "identifier field",
            comparison_intent="identifier-like field",
            normalization_intent="exact identifier normalization",
            identifier_intent="business identifier",
            blocking_intent="exact identifier matching",
        )
    return ColumnSemanticDescriptor(
        semantic_label=detail.description or "text field",
        comparison_intent="generic text similarity",
        normalization_intent="generic text normalization",
        identifier_intent="supporting context",
        blocking_intent="generic fuzzy blocking",
    )


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
        for marker in ["company", "organization", "business", "agency", "provider", "vendor", "site", "school", "hospital", "clinic", "facility"]
    )


def _semantic_mentions_person(evidence: str) -> bool:
    return any(
        marker in evidence
        for marker in ["person", "contact", "director", "customer name", "full name", "individual", "patient"]
    )
