# Dedup Agent Current State Report

## Scope

This report describes the **current live implementation** of the deduplication
agent in this repo after the move to:

- hybrid LLM + deterministic execution
- pre-cleaning HITL strategy review
- user-facing business fields instead of internal row-case review payloads

It is intended to answer:

- what the dedup agent does now
- what state fields it reads and writes
- what the current HITL contract is
- why those HITL fields were added
- what is still deferred

---

## Current Dedup Worker

The deduplication worker is a **hybrid tool-calling agent**.

### Responsibility split

- LLM responsibilities:
  - choose `exact_full_row` or `exact_key`
  - suggest key columns
  - suggest `column_semantics` descriptors such as:
    - `semantic_label`
    - `comparison_intent`
    - `normalization_intent`
    - `identifier_intent`
    - `blocking_intent`
  - use the bounded duplicate-inspection tool during planning
  - when fuzzy is enabled, produce a dataset-specific `fuzzy_plan` that decides:
    - which fuzzy fields to block on
    - which handler strategy each field should use
    - which sub-block columns should split oversized buckets
    - which support/reject evidence fields should classify candidates

- deterministic Python responsibilities:
  - validate the LLM decision
  - apply safe fallback rules
  - privately resolve semantic intents into deterministic execution handlers
  - normalize comparison values
  - validate and sanitize the `fuzzy_plan`
  - build duplicate preview metrics
  - wait for HITL review when required
  - execute actual dedup only after strategy confirmation
  - execute fuzzy candidate generation from the validated plan
  - write parquet output
  - write validation summaries

The important architectural boundary is:

- the LLM decides **what rule to use**
- deterministic code decides **how to apply the rule**

---

## Supported Dedup Behavior

### Exact deterministic dedup

Currently supported:

- exact full-row duplicate removal
- exact key / composite-key dedup
- generic phone normalization for comparison
- generic email normalization for comparison
- Unicode-safe text normalization for fuzzy blocking support
- configurable keep rule for exact key dedup:
  - `keep_most_complete`
  - `keep_first`
  - `keep_last`

### Unsafe exact-key situations still blocked before execution

Without human confirmation, the agent does not trust:

- single technical row IDs as the only dedup key
- weak single-field keys such as phone-only
- name-only key sets without a hard identifier
- cross-script name-only auto-merges

Those concerns are surfaced in review warnings and validation hints instead of
being auto-merged.

### Fuzzy blocking

Fuzzy blocking still exists, but it is not the primary HITL surface anymore.

Current fuzzy behavior:

- runs only when planner strategy signals fuzzy/entity-style intent
- uses a plan-driven `fuzzy_plan` chosen by the LLM
- uses the bounded `profile_fuzzy_columns` tool when the agent needs more dataset-specific fuzzy context
- executes dynamic block keys instead of one fixed blocking rule
- supports plan-driven oversized-bucket handling:
  - `sub_block`
  - `top_k_rank`
  - `truncate`
- classifies candidates deterministically as:
  - `supported`
  - `review`
  - `rejected`
- persists the fuzzy plan in `decision_trace` so reruns can reuse the same orchestration context
- still produces candidate summaries only, not final fuzzy auto-merges

Current fuzzy non-goals:

- no direct row merge
- no sidecar artifact
- no LLM pair classifier
- no dedicated MinHash backend yet; `minhash_lsh` is currently a plan option that falls back to deterministic shingle execution

### `fuzzy_plan`

When fuzzy blocking is enabled, the LLM now proposes a dataset-specific
execution plan instead of relying on one fixed fuzzy configuration.

Current shape:

```python
FuzzyExecutionPlan(
    enabled=True | False,
    entity_scope="freeform dataset-specific scope or None",
    blocking_specs=[...],
    evidence_specs=[...],
    candidate_resolution_policy="freeform policy label",
    notes=[...]
)
```

This was added to push fuzzy behavior away from hardcoded field heuristics.

Why it exists:

- different datasets need different fuzzy fields
- different datasets need different block keys
- different datasets need different oversized-bucket split strategies
- different datasets need different evidence columns for confirming or rejecting a fuzzy candidate

#### `blocking_specs`

Each `BlockingSpec` tells deterministic code:

- a stable `spec_id` for referencing the blocking rule
- which target columns to fuzzy-match
- a freeform `semantic_label` chosen for the current dataset
- a freeform `comparison_intent`
- a freeform `blocking_intent`
- which execution strategy to use, for example:
  - `token_blocking`
  - `ngram_blocking`
  - `word_shingle_blocking`
  - `minhash_lsh`
- which block-key transforms to apply
- how to handle oversized buckets

This is important because fuzzy behavior is now driven by an explicit plan
instead of one hardcoded routine.

Important distinction:

- `semantic_label` is intentionally flexible and dataset-specific
- `comparison_intent` and `blocking_intent` are also flexible and dataset-specific
- deterministic runtime privately resolves those intents into a bounded set of
  executable comparator families

#### `block_keys`

Each block key is a deterministic transform chosen by the plan, for example:

- `normalized_prefix`
- `sorted_token_prefix`
- `domain`
- `area_code`
- `year`
- `exact_normalized`

Why this was added:

- some datasets split best by city or source
- some split best by email domain or phone area
- some do not have those columns at all

So the plan chooses the available, meaningful split logic from the dataset,
and deterministic code executes it.

Important distinction:

- the dataset-dependent decision of **which columns** to use comes from the LLM plan
- the transform labels remain a bounded execution vocabulary because they are
  stable mechanical operations, not business semantics

#### `sub_block_columns`

This is the plan-driven answer to skewed blocking.

Instead of hardcoding:

- region
- year
- source

the LLM can choose whichever columns are actually useful in the current dataset.

Deterministic code then uses those columns to split oversized buckets.

#### `evidence_specs`

These tell deterministic code how to classify a fuzzy candidate:

- which `blocking_specs` they apply to
- which columns support a candidate
- which columns reject a candidate on conflict
- how many support matches are needed

Current deterministic outcomes are:

- `supported`
- `review`
- `rejected`

This is the bridge between:

- fuzzy candidate generation
- later HITL or future pair-level resolution

#### `candidate_resolution_policy`

This tells the agent how conservative to be after fuzzy candidate generation.

Current values:

- `preview_only`
- `hitl_required`

Current implementation remains conservative:

- fuzzy candidates are summarized
- they are not auto-merged into final parquet output

---

## Current HITL Model

The current HITL design is **strategy review before cleaning**.

This means:

1. the agent proposes how dedup should run
2. the user reviews understandable business fields
3. the user can modify those fields
4. the review endpoint only persists those choices
5. only the next `POST /api/v1/dedup/run` performs cleaning

This is intentionally different from the previous row-case review design.

### Why this design was chosen

It reduces agent complexity and gives the user control over business logic:

- the user reviews the dedup strategy **before parquet mutation**
- the user can modify key columns directly
- the user can change the keep rule using simple choices
- the review cycle is always explicit, even when the preview currently shows zero duplicate rows
- the user does not need to understand internal row-case workflow payloads,
  row fingerprints, or low-level merge decisions

This matches the product goal better:

- user decides understandable business logic
- agent handles the mechanics

---

## Current User-Facing HITL Fields

The current review payload is stored as:

- `deduplication_result.pending_strategy_review`

This field was added carefully because it serves as the **durable source of
truth** for a pending dedup review. It is attached to the dedup result instead
of being stored as a top-level global queue.

### `pending_strategy_review`

Model:

```python
DedupStrategyReview(
    review_type="dedup_strategy_review",
    proposed_mode="exact_full_row" | "exact_key",
    proposed_key_columns=[...],
    suggested_identifier_columns=[...],
    ignored_columns=[...],
    keep_rule="keep_most_complete" | "keep_first" | "keep_last",
    questions=[...],
    warnings=[...],
    preview=DedupPreviewSummary(...)
)
```

### What each field is for

#### `review_type`

Purpose:
- identifies this review as a **strategy-level dedup review**

Why it exists:
- keeps the contract explicit for frontend and future extensions
- avoids ambiguous interpretation of the review payload

#### `proposed_mode`

Purpose:
- shows whether the agent currently wants to run:
  - `exact_full_row`
  - `exact_key`

Why it exists:
- user should understand the broad dedup method
- this is a high-level business-safe concept

#### `proposed_key_columns`

Purpose:
- shows which columns the agent proposes to use as the dedup key

Why it exists:
- this is the most important business-facing dedup decision
- user can change it directly

Important note:
- this list can be empty when the validated strategy has been downgraded to
  `exact_full_row`
- in that situation, the review is asking the user to provide a business key
  instead of accepting a technical identifier like `Id`

#### `suggested_identifier_columns`

Purpose:
- shows which columns the agent believes are trustworthy identifiers

Why it exists:
- helps user reason about business identity
- easier to understand than raw internal semantic descriptors
- gives semantic guidance without exposing internal planner jargon

Important note:
- these are suggestions, not forced execution inputs
- the user can accept or ignore them

#### `ignored_columns`

Purpose:
- shows columns the agent believes should not drive dedup

Typical examples:
- technical IDs
- row IDs
- unstable metadata

Why it exists:
- users often know better than the model whether a column is technical,
  synthetic, or not reliable
- exposing this directly is more understandable than exposing internal
  exclusion heuristics

#### `keep_rule`

Purpose:
- decides **which row survives** inside each duplicate group

Why it exists:
- it is business-understandable
- it directly affects output quality
- it is a natural multiple-choice control for users

Current supported values:

- `keep_most_complete`
  - keep the row with more non-empty values
  - best default for cleaning datasets from mixed sources
- `keep_first`
  - keep the first row in current dataset order
- `keep_last`
  - keep the last row in current dataset order

This field was added because:
- user may trust source ordering
- user may prefer completeness over ordering
- this is simpler and safer than exposing low-level row merge internals

#### `questions`

Purpose:
- provide simple business questions for UI display

Current examples:
- Which columns should define the same entity?
- Which columns should be treated as reliable identifiers?
- Which columns should be ignored because they are technical or not trustworthy for deduplication?
- How should one row be kept from each duplicate group?

Why it exists:
- guides the user toward the intended review decisions
- reduces the need to expose internal agent terminology

#### `warnings`

Purpose:
- explain why the current strategy may need review

Examples:
- weak single-key risk
- name-only risk
- high-null key columns removed

Why it exists:
- keeps the user aware of why review was triggered
- preserves important agent reasoning in a short, user-safe format

#### `preview`

Purpose:
- shows the expected impact of the current proposed strategy before cleaning runs

Model:

```python
DedupPreviewSummary(
    duplicate_rows=...,
    duplicate_groups=...,
    sample_groups=[...]
)
```

Why it exists:
- lets the user validate the proposal before mutation
- reduces blind approval of bad keys
- still appears even when `duplicate_rows = 0`, because the repo now requires
  explicit strategy review before any cleaning run

Fields:

- `duplicate_rows`
  - estimated number of rows that would be removed under the proposal
- `duplicate_groups`
  - estimated number of duplicate groups under the proposal
- `sample_groups`
  - small examples to help user verify the proposed logic

---

## HITL Feedback Contract

Human review decisions come back through:

- `GlobalState.hitl_feedback`

This field already existed and remains:

- `str | None`

The agent now uses it actively.

Stored payload:

```python
DeduplicationHitlFeedback(
    key_columns=[...] | None,
    identifier_columns=[...] | None,
    ignored_columns=[...] | None,
    keep_rule="keep_most_complete" | "keep_first" | "keep_last" | None,
    note="..." | None
)
```

### Why these fields were chosen

They are easy for users to understand:

- `key_columns`
  - what defines a duplicate
- `identifier_columns`
  - what fields the user considers trustworthy identifiers
- `ignored_columns`
  - what should not be used
- `keep_rule`
  - how to choose the survivor row
- `note`
  - optional business explanation

These replaced older row-case-style review payloads because those were internal
workflow details, not good user-facing business controls.

---

## State Contract

### Top-level `GlobalState` fields read by dedup

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

### Top-level `GlobalState` fields written by dedup

- `deduplication_result`
- `physical_dataframe_path` when cleaning actually runs
- `current_dataset_version` when cleaning actually runs
- `worker_states`
- `validation_results`
- `hitl_status`
- `hitl_checkpoint`
- `hitl_feedback` cleared after successful consumption
- `current_step`
- `completed_steps`
- `global_errors` on failure

### HITL-related top-level fields

#### `hitl_feedback`

Purpose:
- carries user-approved review choices back into the agent

Why it stays top-level:
- it is an inbound control input to the next dedup rerun
- the review endpoint persists this field, but does not execute cleaning by itself

#### `hitl_status`

Current meanings:
- `pending`
  - waiting for user strategy review
- `approved`
  - review was consumed by a later `dedup/run` and cleaning completed
- `rejected`
  - reserved for future use

#### `hitl_checkpoint`

Purpose:
- marks where HITL was triggered

Current reality:
- this is forward-compatible metadata only
- supervisor-based resume routing is not implemented here yet

---

## Dedup Result Contract

Current persisted result:

```python
DeduplicationResult(
    applied_modes=[...],
    key_columns=[...],
    keep_strategy="keep_most_complete" | "keep_first" | "keep_last" | "keep_first",
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
    pending_strategy_review=...
)
```

### Important note on `pending_strategy_review`

This is the **active durable review state**.

Why it was added:
- `validation_results` is append-only and not suitable as a mutable review queue
- `pending_strategy_review` is typed, stable, and attached to the dedup outcome
- frontend can read it from the existing state endpoint without needing a new top-level state field

Current behavior:
- the first `POST /api/v1/dedup/run` always persists `pending_strategy_review`
- this is true even when the preview currently shows `duplicate_rows = 0`
- the field is cleared only after review feedback is consumed by a later dedup run

### `decision_trace`

Still stores audit metadata only:

- `decision_source`
- `column_semantics`
- `ignore_columns`
- `fuzzy_plan`
- `confidence`
- `reasoning_summary`
- `validation_notes`
- `context_hash`

It does not duplicate:

- final row counts
- final key columns
- final keep strategy

Those remain on `DeduplicationResult`.

---

## Validation Result Contract

`ValidationResultItem` is still used, but only for signaling and audit.

Current dedup usage:

- `failed_rules`
  - execution failures
- `metrics_observed`
  - before/after row counts
  - decision source
  - unresolved collision counts/types
  - fuzzy candidate count
  - fuzzy candidate classification counts
  - whether a pending strategy review exists
  - proposed key columns when review is pending
- `replan_hints`
  - human-readable explanation of why review is needed
- `recommended_next_action`
  - `hitl` when strategy review is pending

Important design rule:

- `validation_results` is **not** the source of truth for the pending review lifecycle
- it is a signaling surface only

This distinction matters because:
- `validation_results` is append-only in this repo
- pending review state must be durable and replaceable, not append-only

---

## API And Testing Path

### Run dedup

Route:

`POST /api/v1/dedup/run`

Request body:

```json
{
  "run_id": "..."
}
```

Behavior:

- if no HITL feedback exists:
  - build strategy review
  - do not clean yet
  - return `hitl_status = "pending"`
  - persist `deduplication_result.pending_strategy_review` into checkpointed state
- if HITL feedback exists:
  - apply approved strategy choices
  - execute cleaning

### Submit HITL strategy review

Route:

`POST /api/v1/dedup/review/{run_id}`

Purpose:
- store user-selected dedup business logic into `hitl_feedback`

Important:
- this route does not rerun dedup automatically
- it only persists review feedback into checkpointed state
- caller still triggers a normal `POST /api/v1/dedup/run`
- that next run is the step that consumes feedback and performs cleaning

### Inspect current state

Route:

`GET /api/v1/pipeline/{run_id}/state`

Key fields to inspect:

- `deduplication_result`
- `deduplication_result.pending_strategy_review`
- `validation_results`
- `hitl_status`
- `physical_dataframe_path`
- `current_dataset_version`

Important verification rule:
- after the first `POST /api/v1/dedup/run`, `GET /api/v1/pipeline/{run_id}/state`
  should show the same persisted `deduplication_result` and `pending_strategy_review`
- if the state endpoint does not show them, then the review endpoint will not be
  able to consume the review cycle correctly

---

## Output File Behavior

When cleaning actually runs:

- primary output:
  - `OUTPUT_DIR/{project_id}_deduplicated.parquet`
- fallback:
  - `.tmp/agentic-data-cleaner/outputs/{project_id}_deduplicated.parquet`

When strategy review is still pending:

- no cleaned parquet is written yet
- `physical_dataframe_path` remains unchanged

This is intentional because the user is reviewing the strategy **before**
data mutation.

---

## Verification Status

Verified locally:

- dedup package compiles successfully
- exact key dedup supports:
  - `keep_most_complete`
  - `keep_first`
  - `keep_last`
- strategy-review HITL flow works as designed:
  - first run emits pending strategy review instead of cleaning immediately
  - feedback is stored through `hitl_feedback`
  - rerun consumes feedback and executes cleaning

---

## Current Limits

- fuzzy candidates are not yet promoted into a richer user-facing review UI
- fuzzy candidates are not yet auto-merged into final dataset mutation
- there is no LLM-assisted pair resolution yet
- there is no dedicated MinHash/LSH execution backend yet
- `hitl_checkpoint` is metadata only in the current slice
- internal debug override still exists for migration/testing

---

## Bottom Line

The current dedup agent is:

- LLM-guided for strategy selection
- deterministic for execution
- strategy-reviewed by humans **before** cleaning
- user-facing in its HITL fields
- repo-aligned in state usage
- non-redundant in persisted fields

The key change is that HITL now reviews **business-friendly strategy fields**
instead of exposing internal row-case workflow fields.
