"""Build repo-aligned validation result payloads for dedup."""

from __future__ import annotations

from typing import Any

from app.graphs.states.output_validation import ValidationResultItem


def build_validation_results(
    *,
    agent_name: str,
    timestamp: str,
    before_row_count: int,
    after_row_count: int,
    decision_source: str,
    failed_rules: list[str],
    unresolved_collisions: list[dict[str, Any]],
    fuzzy_candidate_count: int,
    fuzzy_notes: list[str],
    pending_strategy_review: bool,
    proposed_key_columns: list[str],
) -> list[ValidationResultItem]:
    """Build validation items using the current repo schema."""

    metrics_observed: dict[str, Any] = {
        "before_row_count": before_row_count,
        "after_row_count": after_row_count,
        "decision_source": decision_source,
    }
    replan_hints: dict[str, Any] = {}
    if unresolved_collisions:
        metrics_observed["unresolved_collision_count"] = len(unresolved_collisions)
        metrics_observed["unresolved_collision_types"] = [
            collision.get("collision_type", "unknown") for collision in unresolved_collisions
        ]
        replan_hints["unresolved_collision_reason"] = (
            "Consider adding a second identifying field to resolve weak-key or cross-script collisions."
        )
    if fuzzy_candidate_count:
        metrics_observed["fuzzy_candidate_count"] = fuzzy_candidate_count
    if fuzzy_notes:
        replan_hints["fuzzy_notes"] = fuzzy_notes

    recommended_next_action = "pass" if not failed_rules else "retry_worker"
    if pending_strategy_review:
        metrics_observed["pending_strategy_review"] = True
        metrics_observed["proposed_key_columns"] = proposed_key_columns
        replan_hints["hitl_reason"] = "Dedup strategy review is required before cleaning."
        recommended_next_action = "hitl"

    return [
        ValidationResultItem(
            agent=agent_name,
            task_id="deduplication",
            passed=not failed_rules,
            failed_rules=failed_rules,
            metrics_observed=metrics_observed,
            replan_hints=replan_hints,
            recommended_next_action=recommended_next_action,
            timestamp=timestamp,
        )
    ]
