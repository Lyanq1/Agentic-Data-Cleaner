"""Simple fuzzy blocking for near-duplicate candidate generation."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd

from app.agents.deduplication.column_roles import infer_column_role
from app.agents.deduplication.models import FuzzyBlockingConfig, FuzzyCandidate, FuzzyCandidateSet
from app.agents.deduplication.normalizers import is_cross_script_pair, normalize_text, shingle_text
from app.graphs.states.profiles import SemanticProfile


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _blocking_key(value: object, *, field_type: str) -> str:
    normalized = normalize_text(value, field_type=field_type)
    if not normalized:
        return ""
    if field_type == "address":
        tokens = normalized.split()
        return " ".join(sorted(tokens[:4]))
    compact = normalized.replace(" ", "")
    return compact[:4]


def run_fuzzy_blocking(
    df: pd.DataFrame,
    *,
    key_columns: list[str],
    ignore_columns: list[str],
    column_roles: dict[str, str] | None = None,
    semantic_profile: SemanticProfile | None = None,
    config: FuzzyBlockingConfig | None = None,
) -> FuzzyCandidateSet:
    """Generate fuzzy duplicate candidates without mutating the dataframe."""

    config = config or FuzzyBlockingConfig()
    candidates: list[FuzzyCandidate] = []
    oversized_buckets: list[str] = []
    notes: list[str] = []

    candidate_fields = [
        column
        for column in df.columns
        if column not in ignore_columns
        and infer_column_role(
            column,
            explicit_roles=column_roles,
            semantic_profile=semantic_profile,
        ) in {"address", "company_name", "person_name"}
        and column not in key_columns
    ]

    for column in candidate_fields:
        field_type = infer_column_role(
            column,
            explicit_roles=column_roles,
            semantic_profile=semantic_profile,
        )
        if field_type is None:
            continue
        bucket_map: dict[str, list[tuple[int, str]]] = defaultdict(list)
        for row_index, value in df[column].items():
            key = _blocking_key(value, field_type=field_type)
            if key:
                bucket_map[key].append((int(row_index), str(value)))

        for bucket_key, rows in bucket_map.items():
            if len(rows) < 2:
                continue
            if len(rows) > config.max_bucket_size:
                oversized_buckets.append(f"{column}:{bucket_key}")
                rows = rows[: config.max_bucket_size]
                notes.append(
                    f"Bucket '{column}:{bucket_key}' exceeded {config.max_bucket_size} rows and was capped."
                )

            for index in range(len(rows)):
                left_idx, left_value = rows[index]
                for compare_index in range(index + 1, len(rows)):
                    right_idx, right_value = rows[compare_index]
                    if field_type == "address":
                        left_shingles = shingle_text(left_value, size=config.address_shingle_size, field_type=field_type)
                        right_shingles = shingle_text(right_value, size=config.address_shingle_size, field_type=field_type)
                        threshold = config.address_threshold
                    elif field_type == "company_name":
                        left_shingles = shingle_text(left_value, size=config.company_ngram_size, field_type=field_type)
                        right_shingles = shingle_text(right_value, size=config.company_ngram_size, field_type=field_type)
                        threshold = config.company_threshold
                    else:
                        left_shingles = shingle_text(left_value, size=config.person_ngram_size, field_type=field_type)
                        right_shingles = shingle_text(right_value, size=config.person_ngram_size, field_type=field_type)
                        threshold = config.person_threshold

                    score = _jaccard(left_shingles, right_shingles)
                    if score < threshold:
                        continue

                    candidate_type = field_type
                    if field_type == "person_name" and is_cross_script_pair(left_value, right_value):
                        candidate_type = "cross_script_name"

                    candidates.append(
                        FuzzyCandidate(
                            row_index_a=left_idx,
                            row_index_b=right_idx,
                            field=column,
                            similarity_score=score,
                            blocking_key=bucket_key,
                            candidate_type=candidate_type,
                        )
                    )

    if candidates:
        notes.append(f"Generated {len(candidates)} fuzzy candidate pairs across {len(candidate_fields)} field(s).")
    return FuzzyCandidateSet(candidates=candidates, oversized_buckets=oversized_buckets, notes=notes)
