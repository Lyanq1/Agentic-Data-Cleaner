"""Prompt helpers for dedup strategy selection."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage


DEDUP_DECISION_SYSTEM_PROMPT = """You are the deduplication strategy planner for a data-cleaning pipeline.

Your job is to choose a safe deduplication strategy from the provided dataset context.

Rules:
- Use the available inspection tool before finalizing when you are considering exact_key mode.
- Do not use technical row identifiers as business dedup keys unless there is strong evidence they are true business identifiers.
- Prefer composite business keys over weak single-column keys.
- Avoid key columns with high null rates when possible.
- If evidence is contradictory or weak, return mode=review_needed.
- Return a short reasoning_summary. Do not reveal hidden chain-of-thought.
"""


DEDUP_DECISION_JSON_INSTRUCTION = """Return ONLY a valid JSON object matching this schema:
{
  "mode": "exact_full_row | exact_key | review_needed",
  "key_columns": ["column1", "column2"],
  "ignore_columns": ["column_a"],
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
