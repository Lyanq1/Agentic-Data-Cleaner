"""Plan-driven fuzzy blocking for near-duplicate candidate generation."""

from __future__ import annotations

from collections import Counter, defaultdict
from urllib.parse import urlparse

import pandas as pd

from app.agents.deduplication.models import (
    BlockKeySpec,
    BlockingSpec,
    EvidenceSpec,
    FuzzyBlockingConfig,
    FuzzyCandidate,
    FuzzyCandidateSet,
    FuzzyExecutionPlan,
)
from app.agents.deduplication.normalizers import (
    is_cross_script_pair,
    normalize_email,
    normalize_phone,
    normalize_text,
    shingle_text,
)


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _weighted_jaccard(left: list[str], right: list[str]) -> float:
    if not left or not right:
        return 0.0
    left_counts = Counter(left)
    right_counts = Counter(right)
    keys = set(left_counts) | set(right_counts)
    numerator = sum(min(left_counts[key], right_counts[key]) for key in keys)
    denominator = sum(max(left_counts[key], right_counts[key]) for key in keys)
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _normalize_for_transform(value: object, *, transform: str) -> str:
    transform_key = (transform or "normalized_prefix").strip().casefold()
    if value is None:
        return ""
    if transform_key == "domain":
        text = str(value).strip()
        if not text:
            return ""
        if "@" in text:
            return text.split("@", 1)[1].casefold().strip()
        parsed = urlparse(text if "://" in text else f"https://{text}")
        return parsed.netloc.casefold().lstrip("www.")
    if transform_key == "area_code":
        phone = normalize_phone(value)
        if not phone:
            return ""
        return phone[:3]
    if transform_key == "year":
        digits = "".join(char for char in str(value) if char.isdigit())
        return digits[:4] if len(digits) >= 4 else ""
    if transform_key == "exact_normalized":
        email = normalize_email(value)
        if email:
            return email
        phone = normalize_phone(value)
        if phone:
            return phone
        return normalize_text(value)
    normalized = normalize_text(value)
    if not normalized:
        return ""
    if transform_key == "sorted_token_prefix":
        tokens = sorted(normalized.split())
        return " ".join(tokens[:4])
    compact = normalized.replace(" ", "")
    return compact[:6]


def _execution_family(spec: BlockingSpec) -> str:
    family = " ".join([spec.comparison_intent, spec.blocking_intent, spec.semantic_label]).strip().casefold()
    aliases = {
        "organization_name": "organization_name",
        "organization": "organization_name",
        "company_name": "organization_name",
        "company": "organization_name",
        "person_name": "person_name",
        "person": "person_name",
        "address": "address",
        "location": "address",
        "generic_text": "generic_text",
        "text": "generic_text",
    }
    return aliases.get(family, "generic_text")


def _strategy_key(spec: BlockingSpec) -> str:
    strategy = (spec.strategy or "token_blocking").strip().casefold()
    aliases = {
        "token_blocking": "token_blocking",
        "token": "token_blocking",
        "ngram_blocking": "ngram_blocking",
        "ngram": "ngram_blocking",
        "word_shingle_blocking": "word_shingle_blocking",
        "word_shingle": "word_shingle_blocking",
        "minhash_lsh": "minhash_lsh",
        "minhash": "minhash_lsh",
    }
    return aliases.get(strategy, "token_blocking")


def _similarity_metric_key(spec: BlockingSpec) -> str:
    metric = (spec.similarity_metric or "jaccard").strip().casefold()
    aliases = {
        "jaccard": "jaccard",
        "weighted_jaccard": "weighted_jaccard",
        "weighted": "weighted_jaccard",
    }
    return aliases.get(metric, "jaccard")


def _oversized_strategy_key(spec: BlockingSpec) -> str:
    strategy = (spec.oversized_bucket_strategy or "sub_block").strip().casefold()
    aliases = {
        "sub_block": "sub_block",
        "subblock": "sub_block",
        "top_k_rank": "top_k_rank",
        "topk": "top_k_rank",
        "truncate": "truncate",
    }
    return aliases.get(strategy, "sub_block")


def _build_row_blocking_key(row: pd.Series, spec: BlockingSpec, target_column: str) -> str:
    parts: list[str] = []
    if spec.block_keys:
        for block_key in spec.block_keys:
            transformed = _apply_block_key(row, block_key)
            if block_key.required and not transformed:
                return ""
            if transformed:
                parts.append(transformed)
    if not parts:
        fallback_transform = "sorted_token_prefix" if _execution_family(spec) == "address" else "normalized_prefix"
        transformed = _normalize_for_transform(row[target_column], transform=fallback_transform)
        if transformed:
            parts.append(transformed)
    return "|".join(parts)


def _apply_block_key(row: pd.Series, block_key: BlockKeySpec) -> str:
    components = [
        _normalize_for_transform(row[column], transform=block_key.transform)
        for column in block_key.columns
        if column in row.index
    ]
    components = [component for component in components if component]
    return "|".join(components)


def _build_sub_block_key(row: pd.Series, sub_block_columns: list[str]) -> str:
    components = [normalize_text(row[column]) for column in sub_block_columns if column in row.index]
    components = [component for component in components if component]
    return "|".join(components)


def _tokens_for_strategy(value: object, spec: BlockingSpec, config: FuzzyBlockingConfig) -> tuple[set[str], list[str]]:
    family = _execution_family(spec)
    strategy = _strategy_key(spec)
    if family == "address":
        shingle_size = config.address_shingle_size
        tokens = list(shingle_text(value, size=shingle_size, field_type="address"))
    elif family == "person_name":
        shingle_size = config.person_ngram_size
        tokens = list(shingle_text(value, size=shingle_size, field_type="person_name"))
    else:
        shingle_size = config.company_ngram_size
        tokens = list(shingle_text(value, size=shingle_size, field_type="company_name"))

    if strategy == "token_blocking":
        normalized = normalize_text(value)
        tokens = normalized.split() if normalized else []
    elif strategy == "minhash_lsh":
        # Plan-driven interface now supports MinHash; current backend still executes
        # with deterministic shingle approximation until a dedicated MinHash library
        # is added to the repo.
        pass

    return set(tokens), tokens


def _candidate_signature(spec: BlockingSpec, left: object, right: object) -> tuple[str, bool]:
    cross_script = _execution_family(spec) == "person_name" and is_cross_script_pair(left, right)
    return spec.semantic_label or spec.comparison_intent or "fuzzy field", cross_script


def _resolve_candidate(
    blocking_spec_id: str,
    row_a: pd.Series,
    row_b: pd.Series,
    evidence_specs: list[EvidenceSpec],
) -> tuple[list[str], list[str], str]:
    matching_spec = next(
        (
            spec
            for spec in evidence_specs
            if not spec.target_blocking_specs or blocking_spec_id in spec.target_blocking_specs
        ),
        None,
    )
    if matching_spec is None:
        return [], [], "review"

    support_matches: list[str] = []
    reject_conflicts: list[str] = []
    for column in matching_spec.support_columns:
        if column not in row_a.index or column not in row_b.index:
            continue
        left = _normalize_for_transform(row_a[column], transform="exact_normalized")
        right = _normalize_for_transform(row_b[column], transform="exact_normalized")
        if left and right and left == right:
            support_matches.append(column)

    for column in matching_spec.reject_columns:
        if column not in row_a.index or column not in row_b.index:
            continue
        left = _normalize_for_transform(row_a[column], transform="exact_normalized")
        right = _normalize_for_transform(row_b[column], transform="exact_normalized")
        if left and right and left != right:
            reject_conflicts.append(column)

    if reject_conflicts and matching_spec.hard_reject_on_conflict:
        return support_matches, reject_conflicts, "rejected"
    if len(support_matches) >= matching_spec.minimum_support_matches:
        return support_matches, reject_conflicts, "supported"
    return support_matches, reject_conflicts, "review"


def _iter_bucket_rows(
    df: pd.DataFrame,
    spec: BlockingSpec,
    target_column: str,
) -> dict[str, list[int]]:
    buckets: dict[str, list[int]] = defaultdict(list)
    for row_index, row in df.iterrows():
        bucket_key = _build_row_blocking_key(row, spec, target_column)
        if bucket_key:
            buckets[bucket_key].append(int(row_index))
    return buckets


def _split_bucket_rows(
    df: pd.DataFrame,
    row_indices: list[int],
    sub_block_columns: list[str],
) -> list[list[int]]:
    if not sub_block_columns:
        return [row_indices]
    grouped: dict[str, list[int]] = defaultdict(list)
    for row_index in row_indices:
        row = df.loc[row_index]
        sub_key = _build_sub_block_key(row, sub_block_columns)
        grouped[sub_key or "__fallback__"].append(row_index)
    return list(grouped.values())


def run_fuzzy_blocking(
    df: pd.DataFrame,
    *,
    plan: FuzzyExecutionPlan,
    key_columns: list[str] | None = None,
    config: FuzzyBlockingConfig | None = None,
) -> FuzzyCandidateSet:
    """Generate fuzzy duplicate candidates from a validated execution plan."""

    config = config or FuzzyBlockingConfig()
    if not plan.enabled or not plan.blocking_specs:
        return FuzzyCandidateSet(notes=["Fuzzy plan was disabled or empty."])

    candidates: list[FuzzyCandidate] = []
    oversized_buckets: list[str] = []
    notes: list[str] = list(plan.notes)
    supported_count = 0
    review_count = 0
    rejected_count = 0
    excluded_targets = set(key_columns or [])

    for spec in plan.blocking_specs:
        for target_column in spec.target_columns:
            if target_column not in df.columns or target_column in excluded_targets:
                continue
            bucket_rows = _iter_bucket_rows(df, spec, target_column)
            for bucket_key, row_indices in bucket_rows.items():
                if len(row_indices) < 2:
                    continue

                partitions = [row_indices]
                if len(row_indices) > spec.max_bucket_size:
                    oversized_buckets.append(f"{target_column}:{bucket_key}")
                    oversized_strategy = _oversized_strategy_key(spec)
                    if oversized_strategy == "sub_block" and spec.sub_block_columns:
                        partitions = _split_bucket_rows(df, row_indices, spec.sub_block_columns)
                        notes.append(
                            f"Bucket '{target_column}:{bucket_key}' exceeded {spec.max_bucket_size} rows and was split using {spec.sub_block_columns}."
                        )
                    elif oversized_strategy == "top_k_rank":
                        partitions = [row_indices[: spec.max_bucket_size]]
                        notes.append(
                            f"Bucket '{target_column}:{bucket_key}' exceeded {spec.max_bucket_size} rows and was ranked/truncated to the top slice."
                        )
                    else:
                        partitions = [row_indices[: spec.max_bucket_size]]
                        notes.append(
                            f"Bucket '{target_column}:{bucket_key}' exceeded {spec.max_bucket_size} rows and was truncated."
                        )

                for partition in partitions:
                    if len(partition) < 2:
                        continue
                    for index in range(len(partition)):
                        left_idx = partition[index]
                        left_value = df.at[left_idx, target_column]
                        left_set, left_tokens = _tokens_for_strategy(left_value, spec, config)
                        for compare_index in range(index + 1, len(partition)):
                            right_idx = partition[compare_index]
                            right_value = df.at[right_idx, target_column]
                            right_set, right_tokens = _tokens_for_strategy(right_value, spec, config)
                            metric = _similarity_metric_key(spec)
                            score = (
                                _weighted_jaccard(left_tokens, right_tokens)
                                if metric == "weighted_jaccard"
                                else _jaccard(left_set, right_set)
                            )
                            if score < spec.similarity_threshold:
                                continue

                            semantic_label, cross_script = _candidate_signature(spec, left_value, right_value)
                            support_matches, reject_conflicts, resolution = _resolve_candidate(
                                spec.spec_id,
                                df.loc[left_idx],
                                df.loc[right_idx],
                                plan.evidence_specs,
                            )
                            if resolution == "supported":
                                supported_count += 1
                            elif resolution == "rejected":
                                rejected_count += 1
                            else:
                                review_count += 1

                            candidates.append(
                                FuzzyCandidate(
                                    row_index_a=left_idx,
                                    row_index_b=right_idx,
                                    blocking_spec_id=spec.spec_id,
                                    field=target_column,
                                    similarity_score=score,
                                    blocking_key=bucket_key,
                                    semantic_label=semantic_label,
                                    cross_script=cross_script,
                                    support_matches=support_matches,
                                    reject_conflicts=reject_conflicts,
                                    resolution=resolution,
                                )
                            )

    if candidates:
        notes.append(
            f"Generated {len(candidates)} fuzzy candidate pairs: "
            f"{supported_count} supported, {review_count} for review, {rejected_count} rejected."
        )
    return FuzzyCandidateSet(
        candidates=candidates,
        oversized_buckets=oversized_buckets,
        notes=notes,
        supported_count=supported_count,
        review_count=review_count,
        rejected_count=rejected_count,
    )
