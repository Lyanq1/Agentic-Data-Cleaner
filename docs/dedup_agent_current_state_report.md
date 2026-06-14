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

## End-To-End Runtime Flow

This section describes the live control flow in the order it actually runs.

### Step 1: Load state and dataset

The dedup agent starts from checkpointed `GlobalState` and builds a narrower
runtime input object.

Main inputs used here:

- dataset path
- dataset schema
- statistical profile
- semantic profile
- planner task, if one exists
- prior `deduplication_result`, if one exists
- `hitl_feedback`, if the user has already reviewed the strategy

Why this step exists:

- the full `GlobalState` is too broad to use as the direct execution contract
- the dedup worker needs a stable, local input model
- this also keeps the dedup agent easier to test in isolation

### Step 2: Reuse prior decision if the context is unchanged

The agent computes a `context_hash` from the current dedup-relevant state.

If the previous `decision_trace.context_hash` matches, the agent can reuse the
prior validated dedup decision instead of calling the LLM again.

Why this exists:

- avoids repeated LLM planning for the same dataset context
- keeps reruns stable
- makes the HITL cycle deterministic across retries

### Step 3: Build a new decision when reuse is not possible

If no reusable decision exists, the agent either:

- consumes an internal debug override
- or invokes the LLM with bounded tools

At this stage the LLM proposes:

- dedup mode
- candidate key columns
- `column_semantics`
- optional `fuzzy_plan`
- short rationale summary

Why this exists:

- key choice and semantic interpretation are dataset-dependent
- these are the unstable parts that should not be hardcoded per dataset

### Step 4: Deterministic validation and sanitization

The raw LLM output is never executed directly.

The dedup agent deterministically validates:

- whether columns actually exist
- whether keys are empty
- whether a single-key choice is weak or technical
- whether a name-only key is unsafe
- whether the fuzzy plan uses valid supported transforms and strategies

This stage may:

- keep the proposed exact-key decision
- downgrade to `exact_full_row`
- build a safer fallback decision

Why this exists:

- protects the runtime from invalid LLM output
- protects the user from bad auto-merge choices
- keeps execution bounded and reproducible

### Step 5: Build the strategy review preview

After validation, the agent builds `pending_strategy_review`.

That review contains:

- proposed mode
- proposed key columns
- suggested identifier columns
- ignored columns
- keep rule
- warnings
- preview counts and sample groups

Why this exists:

- the repo now requires explicit review before cleaning
- the user should approve business logic before parquet mutation

### Step 6: First `POST /api/v1/dedup/run` stops before cleaning

If there is no `hitl_feedback` yet, the agent:

- persists `deduplication_result.pending_strategy_review`
- sets `hitl_status = "pending"`
- does not write a deduplicated parquet

Important consequence:

- `applied_modes` is still empty at this stage
- `output_path` may still point to the current source dataset path
- row counts have not changed yet

Why this exists:

- the first run is a strategy preview step
- it is not yet the cleaning step

### Step 7: Review endpoint persists user choices

`POST /api/v1/dedup/review/{run_id}` does not clean data.

It only persists user feedback into:

- `GlobalState.hitl_feedback`

Why this exists:

- review should be explicit and separate from mutation
- it keeps the API contract simple:
  - one endpoint stores review
  - one endpoint executes dedup

### Step 8: Second `POST /api/v1/dedup/run` consumes feedback

When `hitl_feedback` exists, the next dedup run:

- reads the user-approved `key_columns`
- reads `identifier_columns`
- reads `ignored_columns`
- reads `keep_rule`
- rebuilds the validated decision
- performs deterministic cleaning

Why this exists:

- the user, not the raw LLM output, becomes the final business authority
- cleaning only happens after the review cycle is complete

### Step 9: Persist result and validation summary

After execution the agent writes:

- final `deduplication_result`
- output parquet path
- worker state
- validation summary
- cleared `hitl_feedback`
- `hitl_status = "approved"`

At this stage:

- `pending_strategy_review` becomes `null`
- `output_path` should point to the deduplicated parquet
- row counts reflect the true cleaning result

---

## Schema Design Principles

The current dedup schema is intentionally split into three layers:

### 1. User-facing review fields

These are the fields the user can understand and change directly.

Examples:

- `proposed_key_columns`
- `suggested_identifier_columns`
- `ignored_columns`
- `keep_rule`

Why this layer exists:

- users should review business logic, not internal execution details

### 2. Audit and replay fields

These record how the agent arrived at its decision.

Examples:

- `decision_trace`
- `reasoning_summary`
- `validation_notes`
- `context_hash`

Why this layer exists:

- supports reproducibility
- supports reruns
- supports debugging without duplicating final execution facts

### 3. Private deterministic execution fields

These are internal execution concepts that the runtime needs, but the user
should not need to manage directly.

Examples:

- semantic resolver outputs
- normalization handlers
- comparator families
- fuzzy blocking transforms

Why this layer exists:

- execution must stay bounded and safe
- dataset-specific semantics can still stay flexible at the LLM layer

---

## Core Runtime Schemas

This section explains the important models and why their fields exist.

### `DeduplicationAgentInput`

This is the dedup worker's narrowed runtime contract derived from `GlobalState`.

| Field | Purpose | Why it exists |
|---|---|---|
| `project_id` | Run/project identity | Used for output naming and traceability |
| `dataset_path` | Input parquet path | Actual file the agent reads |
| `dataset_schema` | Available columns and types | Needed to validate key choices |
| `user_prompt` | Optional user context | Lets future prompt tuning incorporate user intent |
| `statistical_profile` | Column completeness/uniqueness signals | Helps reject weak or technical keys |
| `semantic_profile` | Semantic hints about columns | Supports semantic interpretation without hardcoded column-name logic |
| `planner_task` | Planner-provided task hint | Allows the planner to influence dedup strategy |
| `retry_count` | Current retry context | Supports resilience and future retry behavior |
| `hitl_feedback` | Persisted user review choices | Second-run execution depends on this |
| `fuzzy_enabled` | Whether fuzzy planning/execution should run | Prevents fuzzy work when the plan does not call for it |

### `DedupDecision`

This is the raw LLM proposal.

| Field | Purpose | Why it exists |
|---|---|---|
| `mode` | Proposed dedup mode | The LLM must choose between exact full-row and exact key behavior |
| `key_columns` | Candidate business keys | Unstable across datasets, so proposed by the LLM |
| `column_semantics` | Flexible per-column meaning | Replaces rigid public role enums |
| `ignore_columns` | Candidate exclusions | Lets the LLM mark technical or irrelevant fields |
| `fuzzy_plan` | Optional fuzzy strategy proposal | Needed only when fuzzy candidate generation is enabled |
| `confidence` | Advisory confidence signal | Used for fallback decisions and audit |
| `reasoning_summary` | Short rationale | Gives human-readable reasoning without storing full chain-of-thought |

### `ColumnSemanticDescriptor`

This is the core flexible semantic contract for a column.

| Field | Purpose | Why it exists |
|---|---|---|
| `semantic_label` | Dataset-specific human label | Allows labels like `school name`, `provider phone`, `journal identifier` |
| `comparison_intent` | High-level comparison meaning | Lets runtime choose the right comparator behavior |
| `normalization_intent` | High-level normalization meaning | Lets runtime route columns to the right deterministic normalizer |
| `identifier_intent` | Strength/type of identity evidence | Helps distinguish strong identifiers from contextual or weak ones |
| `blocking_intent` | High-level fuzzy blocking meaning | Supports flexible fuzzy plans without hardcoding dataset semantics |

Why this model exists:

- dataset semantics vary widely
- the repo should not expose rigid public `column_roles` as if all datasets fit a tiny fixed enum

### `ValidatedDedupDecision`

This is the actual decision the deterministic runtime trusts.

| Field | Purpose | Why it exists |
|---|---|---|
| `mode` | Final safe execution mode | This is what the runtime actually uses |
| `key_columns` | Final safe key set | May differ from raw LLM output after validation |
| `column_semantics` | Sanitized semantic descriptors | Safe internal version of semantic meaning |
| `ignore_columns` | Final exclusions | Needed for exact and fuzzy execution logic |
| `fuzzy_plan` | Validated fuzzy plan | Only trusted after deterministic sanitization |
| `decision_source` | Where the final decision came from | Distinguishes LLM vs fallback vs reused paths |
| `confidence` | Advisory confidence | Audit and fallback context |
| `reasoning_summary` | Short rationale | Audit and operator visibility |
| `keep_rule` | Row survivor policy | Required by exact-key execution and user review |
| `validation_notes` | Changes made during validation | Shows why a proposal was downgraded or altered |
| `unresolved_collisions` | Risk signals found during validation | Feeds warnings and validation summaries |

Why this model exists:

- the raw LLM proposal is not safe enough to execute directly
- this model is the boundary between planning and execution

### `DedupDecisionTrace`

This is the persisted audit/replay trace attached to `DeduplicationResult`.

| Field | Purpose | Why it exists |
|---|---|---|
| `decision_source` | Final source of truth for origin | Helps explain whether LLM or fallback logic drove the run |
| `column_semantics` | Persisted semantic plan | Needed for reruns and debugging |
| `ignore_columns` | Persisted exclusions | Needed for reproducibility |
| `fuzzy_plan` | Persisted fuzzy orchestration | Allows reruns to reuse the same plan |
| `confidence` | Audit confidence | Historical context only |
| `reasoning_summary` | Short rationale | Human-readable audit note |
| `validation_notes` | Validation changes | Explains why the final decision differs from the raw proposal |
| `context_hash` | Dedup-relevant state hash | Enables safe decision reuse on later runs |

Why this model exists:

- reruns should not always require a new LLM call
- audit metadata should not be mixed into final business result fields

### `DedupStrategyReview`

This is the durable user-facing review payload.

| Field | Purpose | Why it exists |
|---|---|---|
| `review_type` | Review contract identity | Future-proofs the payload shape |
| `proposed_mode` | Broad dedup method | User-safe summary of the current plan |
| `proposed_key_columns` | Suggested business key | Main field the user will usually change |
| `suggested_identifier_columns` | Helpful identifier suggestions | Gives business context without exposing internal semantic descriptors directly |
| `ignored_columns` | Candidate exclusions | Lets the user confirm technical fields should be ignored |
| `keep_rule` | Survivor-row policy | User-facing control over final retained row |
| `questions` | Review guidance text | Helps the user understand what they are being asked to decide |
| `warnings` | Risk explanations | Shows why the current strategy needs attention |
| `preview` | Expected impact before cleaning | Lets the user inspect the proposal before mutation |

Why this model exists:

- the repo intentionally moved away from row-level merge-case HITL
- strategy review is simpler, clearer, and safer for the current product

### `DedupPreviewSummary`

This supports the pre-clean review.

| Field | Purpose | Why it exists |
|---|---|---|
| `duplicate_rows` | Estimated rows that would be removed | User wants impact before approval |
| `duplicate_groups` | Estimated duplicate groups | Gives scale beyond raw row count |
| `sample_groups` | Small examples of affected groups | Helps validate the chosen business key |

Why this model exists:

- review without preview would be blind approval

### `DeduplicationHitlFeedback`

This is the persisted user approval/override payload.

| Field | Purpose | Why it exists |
|---|---|---|
| `key_columns` | User-approved dedup key | Main business override field |
| `identifier_columns` | User-confirmed identifier hints | Helps capture business knowledge that the LLM may miss |
| `ignored_columns` | User-confirmed exclusions | Needed when the user knows a field is technical or misleading |
| `keep_rule` | User-approved row retention policy | Lets the user choose survivor behavior |
| `note` | Optional human context | Simple audit note for why the override was chosen |

Why this model exists:

- the review endpoint should accept only understandable business controls

### `DeduplicationResult`

This is the main persisted dedup outcome.

| Field | Purpose | Why it exists |
|---|---|---|
| `applied_modes` | Which actual execution modes removed rows | Separate from planned mode because a pending-review run applies nothing yet |
| `key_columns` | Effective final key columns | Final execution fact, not just proposal |
| `keep_strategy` | Final survivor rule used | Final execution fact |
| `source_path` | Input dataset path used for this run | Audit traceability |
| `output_path` | Resulting dataset path | Needed for downstream workers and inspection |
| `before_row_count` | Row count before execution | Validation and audit |
| `after_row_count` | Row count after execution | Validation and audit |
| `dropped_row_count` | Rows removed | User-facing cleaning impact |
| `full_row_duplicate_count` | Exact full-row removals | Exact dedup audit |
| `key_duplicate_count` | Exact-key removals | Exact dedup audit |
| `duplicate_group_count` | Number of duplicate groups | Impact summary |
| `notes` | Human-readable execution notes | Summarizes what happened without requiring log access |
| `decision_trace` | Audit/replay metadata | Attached to the result, but not mixed into business fields |
| `pending_strategy_review` | Active review state when waiting | Durable review source of truth |

Why this model exists:

- it is the stable persisted contract the rest of the repo reads
- it must support both preview state and final cleaned state

### `FuzzyExecutionPlan`

This is the fuzzy-orchestration plan produced by the LLM and validated by code.

| Field | Purpose | Why it exists |
|---|---|---|
| `enabled` | Whether fuzzy execution should run | Cheap switch for exact-only datasets |
| `entity_scope` | Dataset-specific entity context | Flexible label for the current fuzzy problem |
| `blocking_specs` | Fuzzy blocking rules | Main plan for candidate generation |
| `evidence_specs` | Candidate classification rules | Needed to separate supported/review/rejected candidates |
| `candidate_resolution_policy` | Conservatism setting | Controls how fuzzy results are treated |
| `notes` | Freeform planning notes | Audit/debug context |

Why this model exists:

- fuzzy behavior is dataset-dependent
- but runtime execution still needs a bounded, explicit plan

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

### Example HITL Review Inputs

These are practical example bodies for:

- `POST /api/v1/dedup/review/{run_id}`

They are testing recommendations, not universal truth.
Different business rules may justify different key choices.

#### General childcare/provider-style sample

Use this for the earlier multi-source childcare/provider sample:

```json
{
  "key_columns": ["Site name", "Address", "Phone"],
  "identifier_columns": ["Site name", "Address", "Phone"],
  "ignored_columns": ["Id", "Source"],
  "keep_rule": "keep_most_complete",
  "note": "Use business identity fields for site-level dedup. Ignore technical and source metadata columns."
}
```

#### `.tmp/beer_dirty.csv`

Recommended first test:

```json
{
  "key_columns": ["beer_name", "style", "brewery_name"],
  "identifier_columns": ["beer_name", "brewery_name"],
  "ignored_columns": ["index", "id", "brewery_id"],
  "keep_rule": "keep_most_complete",
  "note": "Deduplicate beer records by beer identity within a brewery, not by technical IDs."
}
```

Stricter packaging-aware test:

```json
{
  "key_columns": ["beer_name", "style", "ounces", "brewery_name"],
  "identifier_columns": ["beer_name", "brewery_name"],
  "ignored_columns": ["index", "id", "brewery_id"],
  "keep_rule": "keep_most_complete",
  "note": "Use package size to avoid merging different packaged variants of the same beer."
}
```

#### `.tmp/flight_dirty.csv`

Safer source-aware test:

```json
{
  "key_columns": ["src", "flight", "sched_dep_time", "sched_arr_time"],
  "identifier_columns": ["flight", "sched_dep_time", "sched_arr_time"],
  "ignored_columns": ["tuple_id", "act_dep_time", "act_arr_time"],
  "keep_rule": "keep_most_complete",
  "note": "Treat source plus scheduled flight identity as the record key. Ignore technical tuple_id and actual-time fields for dedup."
}
```

More aggressive cross-source grouping test:

```json
{
  "key_columns": ["flight", "sched_dep_time", "sched_arr_time"],
  "identifier_columns": ["flight", "sched_dep_time", "sched_arr_time"],
  "ignored_columns": ["tuple_id", "src", "act_dep_time", "act_arr_time"],
  "keep_rule": "keep_most_complete",
  "note": "Test cross-source flight grouping by scheduled identity only."
}
```

#### `.tmp/hospital_dirty.csv`

Hospital-measure record test:

```json
{
  "key_columns": ["ProviderNumber", "MeasureCode"],
  "identifier_columns": ["ProviderNumber", "MeasureCode"],
  "ignored_columns": ["Address2", "Address3", "MeasureName", "Score", "Sample", "Stateavg"],
  "keep_rule": "keep_most_complete",
  "note": "Treat provider plus measure code as the business record."
}
```

Hospital-facility identity test:

```json
{
  "key_columns": ["HospitalName", "Address1", "City", "State", "PhoneNumber"],
  "identifier_columns": ["ProviderNumber", "PhoneNumber"],
  "ignored_columns": ["MeasureCode", "MeasureName", "Condition", "Score", "Sample", "Stateavg"],
  "keep_rule": "keep_most_complete",
  "note": "Treat hospital identity as name plus location plus phone; ignore measure-level columns."
}
```

#### `.tmp/movie_dirty.csv`

Recommended first test:

```json
{
  "key_columns": ["name", "year", "director"],
  "identifier_columns": ["id"],
  "ignored_columns": ["id", "full_cast", "description", "review_count", "rating_count"],
  "keep_rule": "keep_most_complete",
  "note": "Use title, release year, and director as business identity. Ignore IMDb-style technical id for dedup."
}
```

Looser title-year test:

```json
{
  "key_columns": ["name", "year"],
  "identifier_columns": ["name", "year", "director"],
  "ignored_columns": ["id", "full_cast", "description"],
  "keep_rule": "keep_most_complete",
  "note": "Test title-plus-year grouping, with director as supporting identity context."
}
```

#### `.tmp/tax_dirty.csv`

Safer person-plus-contact test:

```json
{
  "key_columns": ["f_name", "l_name", "phone", "zip"],
  "identifier_columns": ["phone", "zip"],
  "ignored_columns": ["area_code"],
  "keep_rule": "keep_most_complete",
  "note": "Use person identity plus contact and ZIP. Do not treat phone alone as a unique identifier."
}
```

Slightly looser person-plus-phone test:

```json
{
  "key_columns": ["f_name", "l_name", "phone"],
  "identifier_columns": ["phone"],
  "ignored_columns": ["area_code"],
  "keep_rule": "keep_most_complete",
  "note": "Test person-level dedup with phone support, but still avoid phone-only matching."
}
```

#### `.tmp/rayyan_dirty.csv`

Publication metadata test:

```json
{
  "key_columns": ["article_title", "journal_issn", "article_jcreated_at"],
  "identifier_columns": ["journal_issn"],
  "ignored_columns": ["id", "jounral_abbreviation", "article_pagination"],
  "keep_rule": "keep_most_complete",
  "note": "Use publication title plus journal identifier plus publication date as article identity. Ignore technical row id."
}
```

Looser publication identity test:

```json
{
  "key_columns": ["article_title", "journal_title"],
  "identifier_columns": ["journal_issn"],
  "ignored_columns": ["id", "jounral_abbreviation", "article_pagination"],
  "keep_rule": "keep_most_complete",
  "note": "Test article title plus journal title grouping, with journal ISSN as supporting identity context."
}
```

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
