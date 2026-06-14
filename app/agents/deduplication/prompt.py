"""Prompt helpers for dedup strategy selection."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage


DEDUP_DECISION_SYSTEM_PROMPT = """You are the deduplication strategy planner for a data-cleaning pipeline.

Your job is to choose a safe deduplication strategy from the provided dataset context.

Rules:
- Use the available inspection tool before finalizing when you are considering exact_key mode.
- When fuzzy planning is enabled, use the available fuzzy profiling tool before finalizing blocking or oversized-bucket plans.
- Do not use technical row identifiers as business dedup keys unless there is strong evidence they are true business identifiers.
- Prefer composite business keys over weak single-column keys.
- Avoid key columns with high null rates when possible.
- Assign flexible semantic descriptors to relevant columns so deterministic handlers can privately resolve normalization and comparison behavior.
- Use dataset-specific semantic labels and intents instead of forcing all columns into a small universal label set.
- Include descriptors for non-key columns too when they should participate in fuzzy blocking later.
- When fuzzy planning is enabled, choose dataset-specific blocking and evidence rules instead of assuming fixed fields.
- Prefer semantic plans that use whatever columns are actually available in the dataset.
- Do not rely on fuzzy similarity alone for final merging. Fuzzy logic should generate candidates and evidence rules, not unsafe direct merges.
- If evidence is contradictory or weak, prefer exact_full_row over risky key-based merging.
- Return a short reasoning_summary. Do not reveal hidden chain-of-thought.
"""


DEDUP_DECISION_JSON_INSTRUCTION = """Return ONLY a valid JSON object matching this schema:
{
  "mode": "exact_full_row | exact_key",
  "key_columns": ["column1", "column2"],
  "column_semantics": {
    "Phone": {
      "semantic_label": "primary contact phone",
      "comparison_intent": "phone-like identifier",
      "normalization_intent": "phone canonicalization",
      "identifier_intent": "contact identifier",
      "blocking_intent": "exact identifier matching"
    },
    "School": {
      "semantic_label": "school name",
      "comparison_intent": "organization-like entity name",
      "normalization_intent": "organization name normalization",
      "identifier_intent": "entity name context",
      "blocking_intent": "name-based fuzzy blocking with support from city and source"
    }
  },
  "ignore_columns": ["column_a"],
  "fuzzy_plan": {
    "enabled": true,
    "entity_scope": "freeform dataset-specific entity scope or null",
    "blocking_specs": [
      {
        "spec_id": "org_name_primary",
        "target_columns": ["Company Name"],
        "semantic_label": "organization name",
        "comparison_intent": "organization-like entity name",
        "blocking_intent": "name-based fuzzy blocking with support from city and source",
        "strategy": "freeform execution strategy label such as token_blocking, ngram_blocking, word_shingle_blocking, minhash_lsh",
        "block_keys": [
          {
            "columns": ["Source"],
            "transform": "freeform transform label such as normalized_prefix, sorted_token_prefix, domain, area_code, year, exact_normalized",
            "required": false
          }
        ],
        "sub_block_columns": ["City"],
        "similarity_metric": "freeform metric label such as jaccard or weighted_jaccard",
        "similarity_threshold": 0.0,
        "max_bucket_size": 500,
        "oversized_bucket_strategy": "freeform strategy label such as sub_block, top_k_rank, truncate"
      }
    ],
    "evidence_specs": [
      {
        "target_blocking_specs": ["org_name_primary"],
        "support_columns": ["Phone", "Email"],
        "reject_columns": ["Tax ID"],
        "minimum_support_matches": 1,
        "hard_reject_on_conflict": true
      }
    ],
    "candidate_resolution_policy": "freeform policy label such as preview_only or hitl_required",
    "notes": ["short note"]
  },
  "confidence": 0.0,
  "reasoning_summary": "short rationale"
}
Do not wrap the JSON in markdown fences.
"""


def build_dedup_messages(context: dict[str, Any]) -> list:
    """Build the LLM messages used for tool-calling and final JSON decision."""

    pretty = json.dumps(context, indent=2, ensure_ascii=False, default=str)
    return [
        SystemMessage(content=DEDUP_DECISION_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                "Choose the safest deduplication strategy for this dataset.\n\n"
                f"Context:\n```json\n{pretty}\n```"
            )
        ),
    ]
