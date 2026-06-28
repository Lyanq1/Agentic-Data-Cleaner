# Dedup Agent Current State Report

## Scope

This report describes the **current live dedup implementation** after the move
to:

- planner-owned strategy review
- dedup-owned runtime validation and execution
- full workflow integration with planner -> worker -> validator

It focuses on:

- what dedup does now
- what fields it reads and writes
- why those fields exist
- how it fits into the full workflow

---

## Current Role of the Dedup Worker

The dedup worker is now a **runtime execution worker**, not the primary owner
of plan approval.

Responsibility split:

- planner owns:
  - task order
  - dedup strategy intent
  - user-facing review payload before execution
- dedup owns:
  - validating the planner strategy against the real dataframe
  - resolving semantic intent into deterministic handlers
  - executing exact dedup and fuzzy candidate generation
  - returning execution results for validator

This is the intended authority boundary:

- planner decides **what should happen**
- dedup decides **how to execute it safely**

---

## Full Workflow Placement

Dedup runs inside the merged graph workflow:

1. `profiler`
2. `semantic_profile`
3. `input_validator`
4. `planner`
5. plan approval
6. `deduplication`
7. `validator`
8. `null_handling`
9. `validator`
10. `type_casting`
11. `validator`
12. `report_agent`

Why this matters:

- dedup is not a standalone pipeline anymore
- downstream workers read persisted approved state, not temporary HTTP response
  payloads
- validator remains the promotion gate between workers

---

## Current Approval Model

### Primary approval

Primary pre-execution approval is now planner-owned.

It comes from:

- `ExecutionPlan.review`
- approved via:
  - `POST /api/v1/pipeline/{run_id}/approve_plan`

Editable dedup review fields submitted through that endpoint:

- `dedup_review.key_columns`
- `dedup_review.identifier_columns`
- `dedup_review.ignored_columns`
- `dedup_review.keep_rule`

What happens on approval:

- planner-owned dedup review values are validated against `dataset_schema`
- the dedup task inside `execution_plan.task_list` is patched in-place
- the dedup review payload inside `execution_plan.review` is updated to reflect
  the approved values
- the graph resumes from the planner checkpoint

### What was removed

The following dedup-local approval flow is no longer part of the active
contract:

- `POST /api/v1/dedup/review/{run_id}`
- `DedupStrategyReview`
- `DeduplicationHitlFeedback`
- `DeduplicationResult.pending_strategy_review`
- worker-local `hitl_feedback` consumption inside dedup

### What remains

- planner-owned approval is the only active pre-execution dedup HITL path
- dedup runs only through the normal pipeline worker flow
- it no longer drives a separate worker-local approval cycle

---

## End-to-End Dedup Runtime Flow

### Step 1: Build runtime input from `GlobalState`

Dedup narrows `GlobalState` into a worker-specific input contract.

Fields used:

- `project_id`
- `dataset_path`
- `dataset_schema`
- `user_prompt`
- `statistical_profile`
- `semantic_profile`
- `execution_plan`
- `retry_count`

Why:

- the worker should not execute directly against the full global state blob
- a narrow runtime contract is easier to validate and test

### Step 2: Load the current dataframe

Dedup reads the current dataset path from:

- `physical_dataframe_path`
- fallback `dataset_path`

Why:

- this is the worker-path convention already used in the workflow
- the validator and later workers rely on persisted path-based handoff

### Step 3: Reuse prior decision when context matches

If the previous `DedupDecisionTrace.context_hash` matches the current dedup
context, the worker can rebuild and reuse the previous validated decision.

Why:

- avoids unnecessary repeated LLM planning
- stabilizes reruns

### Step 4: Prefer planner-owned strategy

If no reusable decision exists, dedup now first tries to build its runtime
decision from the planner-owned dedup task.

That includes:

- primary keys
- ignored columns
- keep rule
- semantic/fuzzy hints from planner strategy

Why:

- planner now owns the primary dedup strategy intent

### Step 5: Fall back to local LLM planning only when needed

If there is no reusable decision and planner strategy is insufficient, dedup can
still invoke its own LLM-guided planning.

Why:

- this preserves worker robustness
- planner owns the primary path, but dedup still needs a safety fallback

### Step 6: Deterministically validate the chosen decision

Dedup never executes raw LLM or raw planner intent directly.

It validates:

- column existence
- unsafe technical identifiers
- weak single-key choices
- name-only key risks
- fuzzy plan compatibility with available columns

Why:

- planner owns intent, not safety
- worker must still reject unsafe runtime choices

### Step 7: Execute dedup

Current deterministic execution includes:

- exact full-row dedup
- exact key / composite-key dedup
- generic phone normalization
- generic email normalization
- plan-driven fuzzy candidate generation

### Step 8: Return worker output for validator

Dedup writes:

- `deduplication_result`
- `physical_dataframe_path`
- `current_dataset_version`
- `worker_states`
- `validation_results`
- `current_step`
- `completed_steps`

This is the same integration pattern expected of the other workers.

---

## Active Schemas and Why They Exist

## `DeduplicationAgentInput`

Purpose:
- narrowed runtime input for the worker

Fields:

- `project_id`
  - output naming and traceability
- `dataset_path`
  - file the worker reads
- `dataset_schema`
  - validates planner-selected keys
- `user_prompt`
  - optional context for LLM fallback
- `statistical_profile`
  - uniqueness/null signals
- `semantic_profile`
  - semantic hints for normalization and comparison
- `planner_task`
  - planner-owned dedup task
- `retry_count`
  - retry context
- `fuzzy_enabled`
  - whether fuzzy candidate generation should run

Why this model exists:
- avoid passing the entire `GlobalState` into every execution helper

## `DedupDecision`

Purpose:
- raw LLM proposal when local planning is required

Fields:

- `mode`
- `key_columns`
- `column_semantics`
- `ignore_columns`
- `fuzzy_plan`
- `confidence`
- `reasoning_summary`

Why it exists:
- separates raw planning output from validated execution input

## `ValidatedDedupDecision`

Purpose:
- the actual execution decision trusted by the runtime

Fields:

- `mode`
- `key_columns`
- `column_semantics`
- `ignore_columns`
- `fuzzy_plan`
- `decision_source`
- `confidence`
- `reasoning_summary`
- `keep_rule`
- `validation_notes`
- `unresolved_collisions`

Why it exists:
- raw planner/LLM intent must be sanitized before execution

## `DedupDecisionTrace`

Purpose:
- audit and replay metadata persisted inside the result

Fields:

- `decision_source`
- `column_semantics`
- `ignore_columns`
- `fuzzy_plan`
- `confidence`
- `reasoning_summary`
- `validation_notes`
- `context_hash`

Why it exists:
- rerun reuse
- debugging
- reproducibility

## `DeduplicationResult`

Purpose:
- final persisted worker output contract

Fields:

- `applied_modes`
  - which execution modes actually removed rows
- `key_columns`
  - effective key columns actually used
- `keep_strategy`
  - final survivor rule used
- `source_path`
  - input path for this worker run
- `output_path`
  - output path produced by this worker run
- `before_row_count`
  - row count before execution
- `after_row_count`
  - row count after execution
- `dropped_row_count`
  - how many rows were removed
- `full_row_duplicate_count`
  - exact full-row removal count
- `key_duplicate_count`
  - exact-key removal count
- `duplicate_group_count`
  - duplicate group count
- `notes`
  - human-readable worker summary
- `decision_trace`
  - audit/replay metadata

Why this model exists:
- downstream systems should read one stable worker result object

---

## What Dedup Reads from Global State

- `dataset_path`
- `physical_dataframe_path`
- `dataset_schema`
- `user_prompt`
- `statistical_profile`
- `semantic_profile`
- `execution_plan`
- `retry_count`
- `worker_states`
- `deduplication_result`

Why these matter:

- they provide the current data source
- planner intent
- execution context
- and prior decision reuse metadata

---

## What Dedup Writes to Global State

- `deduplication_result`
- `physical_dataframe_path`
- `current_dataset_version`
- `worker_states`
- `validation_results`
- `current_step`
- `completed_steps`
- `hitl_checkpoint`
  - cleared by dedup after execution

Why these writes exist:

- downstream workers and APIs depend on persisted state, not local variables

---

## Fuzzy Execution Status

Fuzzy execution is still supported as **candidate generation**, not final merge.

Current behavior:

- planner or worker planning may enable fuzzy
- worker validates the fuzzy plan
- worker executes bounded blocking/candidate logic
- worker returns candidate summary metrics

Still not active:

- direct fuzzy auto-merge into final dataset
- pair-level LLM entity resolution
- dedicated MinHash backend

---

## Validation Contract

Dedup uses `ValidationResultItem` only as a signaling and audit surface.

Typical dedup metrics written there:

- before/after row count
- decision source
- unresolved collision counts/types
- fuzzy candidate counts

Why this matters:

- `validation_results` is not the worker result object
- `DeduplicationResult` is the worker result object

---

## Current Limits

- planner review is primary, but other workers still need full lineage-first
  alignment in later phases
- dedup still contains fallback local planning for resilience
- validator is not yet the only authoritative lineage promotion point across
  every worker
- final report approval is still a later phase

---

## Bottom Line

The dedup worker is now repo-aligned:

- planner owns primary strategy approval
- planner approval can now override dedup business fields before execution
- dedup owns safe execution
- validator remains the promotion gate
- worker-local review state and review endpoint have been removed from the
  active contract
