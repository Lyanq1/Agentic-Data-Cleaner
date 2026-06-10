  # Dedup Agent Current State Report

  ## Scope

  This report reflects the current deduplication implementation in the repo after the hybrid refactor. It documents the live behavior, the state contract it uses, the testing path, and the remaining limitations.

  ## Current Dedup Worker

  The deduplication worker is now a hybrid LLM tool-calling agent.

  Responsibility split:

  - LLM:
    - chooses `exact_full_row` or `exact_key`
    - suggests key columns
    - returns a per-column semantic handler plan
    - uses the bounded duplicate-inspection tool during strategy selection
  - deterministic Python:
    - validates the LLM decision
    - applies fallback rules
    - performs dataframe mutation
    - writes parquet output
    - generates fuzzy candidates
    - writes validation results

  ## Supported Behavior

  ### Exact deterministic dedup

  - exact full-row duplicate removal with `keep="first"`
  - exact key / composite-key dedup
  - LLM-role-first column handler dispatch
  - semantic-profile inference only when the LLM did not provide a role
  - comparison-only generic phone normalization
  - comparison-only email normalization
  - generic Unicode-safe text normalization for fuzzy blocking
  - `most_complete` tie-breaking for key duplicate groups
    - fewest nulls wins
    - stable first occurrence wins ties
  - HITL review-case emission for ambiguous cases
  - HITL feedback consumption on rerun via `hitl_feedback`

  ### Unsafe deterministic cases now blocked

  - single technical row IDs as the only dedup key
  - single weak identifiers such as phone-only
  - name-only key sets with no hard identifier support
  - cross-script name-only auto-merges

  These cases are preserved, not merged, and surfaced through:

  - `deduplication_result.notes`
  - `deduplication_result.pending_review_cases`
  - `validation_results[*].metrics_observed`
  - `validation_results[*].replan_hints`

  ### Fuzzy blocking

  Fuzzy candidate generation is implemented but gated.

  It runs only when the planner signals fuzzy/entity-style dedup intent through existing planning structures.

Current fuzzy behavior:

- field-role detection prefers the LLM-selected role plan, then semantic profile
- normalized text blocking
  - n-gram / shingle similarity
  - Jaccard scoring inside buckets
  - oversized bucket capping
  - candidate summary only

  Current fuzzy non-goals:

  - no row merge
  - no sidecar artifact
  - no LLM pair classification

  ## HITL

  HITL is now supported for ambiguous dedup cases.

  Current behavior:

  - pending review cases are persisted in:
    - `deduplication_result.pending_review_cases`
  - `validation_results` signals review requirement only:
    - `recommended_next_action = "hitl"`
    - pending case counts and IDs in `metrics_observed`
  - human decisions are submitted as serialized JSON into:
    - `GlobalState.hitl_feedback`
  - on rerun, dedup consumes that feedback and:
    - merges approved cases with `most_complete` keep logic
    - leaves rejected cases unchanged
    - removes resolved cases from `pending_review_cases`

  `hitl_status` usage:

  - `"pending"` when review cases exist
  - `"approved"` when submitted feedback resolves all pending cases
  - `"rejected"` remains reserved and is not set by dedup in the current slice

  ## State Contract

  ### Existing top-level fields used

  From `GlobalState`, the dedup agent reads:

  - `dataset_path`
  - `physical_dataframe_path`
  - `dataset_schema`
  - `user_prompt`
  - `statistical_profile`
  - `semantic_profile`
  - `execution_plan`
  - `task_list`
  - `retry_count`
  - `hitl_feedback`
  - `worker_states`
  - `deduplication_result`

  The agent writes:

  - `deduplication_result`
  - `physical_dataframe_path`
  - `current_dataset_version`
  - `worker_states`
  - `validation_results`
  - `current_step`
  - `completed_steps`
  - `global_errors` on failure

  ### No redundant top-level dedup fields added

  No new top-level `GlobalState` field was introduced for:

  - decision trace
  - fuzzy candidate path
  - unresolved collisions

  Those concerns are handled through existing structures instead.

  HITL-related top-level fields used:

  - `hitl_feedback`
  - `hitl_status`
  - `hitl_checkpoint`

  ## Dedup Result Contract

  The persisted dedup result remains:

  ```python
  DeduplicationResult(
      applied_modes=[...],
      key_columns=[...],
      keep_strategy="first" | "most_complete",
      source_path="...",
      output_path="...",
      before_row_count=...,
      after_row_count=...,
      dropped_row_count=...,
      full_row_duplicate_count=...,
      key_duplicate_count=...,
      duplicate_group_count=...,
      notes=[...],
      decision_trace=...,
      pending_review_cases=[...]
  )
  ```

  ### Decision trace remains minimal

  `decision_trace` stores audit metadata only:

  - `decision_source`
  - `column_roles`
  - `ignore_columns`
  - `confidence`
  - `reasoning_summary`
  - `validation_notes`
  - `context_hash`

  It does not duplicate:

  - applied execution modes
  - final key columns
  - row counts

  Those remain on `DeduplicationResult`.

  ## Validation Result Contract

  The dedup agent uses the existing `ValidationResultItem` schema.

  It does not add `rule` or `severity`.

  Current usage:

  - `failed_rules`
    - row-count or duplicate-removal failures
  - `metrics_observed`
    - before/after row counts
    - decision source
    - unresolved collision counts/types
    - fuzzy candidate count
  - `replan_hints`
    - safer follow-up guidance when unresolved collisions were detected
    - fuzzy notes when fuzzy blocking ran
    - HITL guidance when pending review cases exist

  `validation_results` is not the source of truth for pending review lifecycle.
  It is signaling and audit only.

  ## API And Testing Path

  ### Public route

  `POST /api/v1/dedup/run`

  Request body:

  ```json
  {
    "run_id": "..."
  }
  ```

  ### Internal testing override

  The service layer still supports a private debug override for key columns.

  It is not part of the public route schema.

  ### HITL feedback route

  `POST /api/v1/dedup/review/{run_id}`

  This persists accepted human decisions into `hitl_feedback`.
  It does not rerun the dedup agent automatically.

  ### State inspection

  Use:

  `GET /api/v1/pipeline/{run_id}/state`

  Key fields to inspect:

  - `physical_dataframe_path`
  - `deduplication_result`
  - `deduplication_result.pending_review_cases`
  - `worker_states`
  - `validation_results`
  - `current_dataset_version`
  - `hitl_status`

  ## Output File Behavior

  Primary output path:

  ```text
  OUTPUT_DIR/{project_id}_deduplicated.parquet
  ```

  If the configured output directory is not writable in the current environment, the worker falls back to:

  ```text
  .tmp/agentic-data-cleaner/outputs/{project_id}_deduplicated.parquet
  ```

  ## Verification Status

  Verified locally after the refactor:

  - dedup package compiles successfully
  - a smoke test with normalized `Phone + Email` duplicates removed one row correctly
  - exact key dedup returned:
    - `applied_modes = ["exact_key"]`
    - `keep_strategy = "most_complete"`
    - normalized comparison notes

  ## Current Limits

  - fuzzy candidates are not persisted as a standalone artifact
  - there is no LLM-assisted pair resolution yet
  - `hitl_checkpoint` is written as forward-compatible metadata only; supervisor resume routing is not implemented here
  - internal debug overrides are still available during migration and intentionally bypass the LLM path

  ## Bottom Line

  The current dedup agent is no longer a pure pandas worker.

  It is now:

  - LLM-guided for strategy selection
  - deterministic for execution
  - dataset-agnostic in its normalization layer
  - async HITL-capable for ambiguous cases
  - repo-aligned in state usage
  - non-redundant in persisted fields
  - able to reject risky exact-key merges and surface them without inventing new schema
