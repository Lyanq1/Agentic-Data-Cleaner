# Dedup Agent Current State Report

## Scope

This report documents the current deduplication worker state in the repo, the exact schema changes made for the worker, the current API testing path, and the expected output and verification flow.

This report is intentionally precise about:

- which fields already existed
- which fields were added
- which fields are internal-only
- which fields are exposed publicly
- where there is still duplication in the current design

## Current Dedup Worker Scope

The current deduplication worker is a deterministic pandas-based worker. It does not call an LLM.

Current supported use cases:

1. Exact full-row duplicates
- Uses `df.drop_duplicates(keep="first")`
- Removes rows only when every column matches

2. Exact key-based duplicates
- Uses `df.drop_duplicates(subset=key_columns, keep="first")`
- Runs when a key is explicitly provided or inferred from planner/profile

3. No-op dedup pass
- If no duplicates are found, the worker still writes an output parquet and records a dedup result

Current non-goals:

- fuzzy matching
- MinHash / LSH
- phone normalization
- email normalization
- cross-language matching
- conflict resolution such as `keep_most_complete`
- merge of partial records

## Exact Schema Audit

### 1. `GlobalState` fields that already existed before the current endpoint work

These fields already existed in `app/graphs/states/global_state.py` and were not introduced by the dedup debug endpoint work:

- `dataset_path`
- `dataset_schema`
- `user_prompt`
- `current_dataset_version`
- `physical_dataframe_path`
- `current_step`
- `completed_steps`
- `statistical_profile`
- `semantic_profile`
- `input_validation_result`
- `execution_plan`
- `worker_states`
- `validation_results`
- `current_task_idx`
- `retry_count`
- `global_errors`

### 2. `GlobalState` fields added for dedup support

These were added in `app/graphs/states/global_state.py`:

#### `DeduplicationResult`

New typed model:

```python
class DeduplicationResult(BaseModel):
    applied_modes: List[Literal["exact_full_row", "exact_key"]] = Field(default_factory=list)
    key_columns: List[str] = Field(default_factory=list)
    keep_strategy: str = "first"
    source_path: str
    output_path: str
    before_row_count: int
    after_row_count: int
    dropped_row_count: int
    full_row_duplicate_count: int = 0
    key_duplicate_count: int = 0
    duplicate_group_count: int = 0
    notes: List[str] = Field(default_factory=list)
```

Why this field is needed:

- the dedup worker needs a structured result payload
- row counts and mode applied should not be inferred from logs
- output path should be kept in a typed result, not only in `physical_dataframe_path`

#### `deduplication_result`

New top-level state field:

```python
deduplication_result: Optional[DeduplicationResult]
```

Why this field is needed:

- `physical_dataframe_path` only tells where the output dataset is
- it does not describe what dedup logic was applied
- dedup metrics need a stable home in state

### 3. `task_list` audit

Current `GlobalState` also contains:

```python
task_list: Optional[List[str]]
execution_plan: Optional[ExecutionPlan]
```

This is the main current duplication in the state model.

Why both exist today:

- `execution_plan.task_list` is the typed planner output
- top-level `task_list` is the simplified router list used by the graph supervisor

Where top-level `task_list` is currently used:

- `app/graphs/graph.py`
- `app/graphs/nodes.py`
- `app/agents/planner/agent.py`

Conclusion:

- yes, this is duplicated information
- no, it was not introduced by the dedup debug endpoint
- it should remain for now because the graph router depends on it
- if we want to remove it later, that is a separate graph/planner refactor

## Public API Schema Audit

### Existing endpoint

`GET /api/v1/pipeline/{run_id}/state`

Original public shape already included:

- `run_id`
- `dataset_path`
- `dataset_schema`
- `user_prompt`
- `statistical_profile`
- `data_profile`
- `semantic_profile`
- `input_validation_result`
- `current_step`
- `completed_steps`
- `errors`
- `next_node`

### Additional public fields kept for dedup inspection

Only these extra fields are now exposed publicly because they are needed to inspect dedup execution:

- `physical_dataframe_path`
- `worker_states`
- `validation_results`
- `deduplication_result`
- `current_dataset_version`

Why each is needed:

- `physical_dataframe_path`
  - tells where the current deduped dataset version is written

- `worker_states`
  - shows whether the dedup worker finished or failed

- `validation_results`
  - shows the worker-level pass/fail validation entry

- `deduplication_result`
  - contains dedup metrics and notes

- `current_dataset_version`
  - identifies that the current dataframe is now the dedup output version

### Fields intentionally not exposed publicly

These are still available internally in the checkpointed raw state, but are not returned from `GET /state`:

- `task_list`
- `execution_plan`

Why:

- they are not required to inspect dedup output
- exposing both creates duplicate planning representations in the public response
- the dedup debug endpoint uses the internal raw checkpoint state directly and does not need them in the public state payload

## New File Audit

### `app/api/v1/deduplication.py`

Why this file was added:

- the current graph stops before `supervisor`
- dedup cannot be reached through `POST /api/v1/pipeline/run`
- the repo had no direct endpoint for running only the dedup worker

This file provides:

- `POST /api/v1/dedup/run`

Request:

```json
{
  "run_id": "483d2083455c",
  "key_columns": ["Id"]
}
```

Behavior:

1. load checkpointed state by `run_id`
2. inject the requested `key_columns` into a working dedup task
3. run `DeduplicationAgent`
4. persist dedup output back into the checkpointed run state
5. return the updated dedup-facing state

### Internal service helpers added in `app/services/pipeline.py`

Added internal helpers:

- `get_pipeline_raw_state(run_id)`
- `_inject_dedup_key_columns(state, key_columns)`
- `run_dedup_agent_for_run(run_id, key_columns=None)`

Why they are needed:

- `get_pipeline_state()` returns the public view, not the raw checkpoint payload
- the dedup worker needs the real saved state
- the debug endpoint needs a safe place to inject requested key columns without changing the public state schema

## Current Dedup Agent Behavior

### Inputs used by the worker

The dedup worker reads from `GlobalState`:

- `physical_dataframe_path` or `dataset_path`
- `dataset_schema`
- `statistical_profile`
- `execution_plan`
- `retry_count`
- `hitl_feedback`

### Output fields written by the worker

The dedup worker returns:

- `deduplication_result`
- `physical_dataframe_path`
- `current_dataset_version`
- `worker_states`
- `validation_results`
- `current_step`
- `completed_steps`

### Why these output fields are needed

- `deduplication_result`
  - summary metrics and mode used

- `physical_dataframe_path`
  - concrete path to the new dataset version

- `current_dataset_version`
  - tracks the stage label of the current dataset

- `worker_states`
  - worker-level success/failure state

- `validation_results`
  - self-validation artifact written by the worker

## Current Testing Flow

### 1. Run the normal pipeline first

Use:

```http
POST /api/v1/pipeline/run
```

This creates the checkpointed state and `run_id`.

### 2. Run the dedup worker directly

Use:

```http
POST /api/v1/dedup/run
Content-Type: application/json

{
  "run_id": "483d2083455c",
  "key_columns": ["Id"]  
}
```
key_columns is optional:

  - if omitted, the agent can still run exact full-row dedup
  - if provided, the agent will also check exact key-based duplicates using those columns

  You can pass one or many keys:

  {
    "run_id": "483d2083455c",
    "key_columns": ["Id"]
  }

  {
    "run_id": "483d2083455c",
    "key_columns": ["Phone", "Email"]
  }

### 3. Inspect the updated state

Use:

```http
GET /api/v1/pipeline/483d2083455c/state
```

Inspect these fields:

- `physical_dataframe_path`
- `deduplication_result`
- `worker_states`
- `validation_results`
- `current_dataset_version`

## Expected Output for the Current Sample State

Given the current sample state:

- `statistical_profile.duplicate_rows = 0`
- `pk_candidates = ["Id"]`
- `Id` is unique across all rows

Expected dedup result:

- no full-row duplicates removed
- no key-based duplicates removed on `Id`
- output parquet still written
- dedup result still recorded

Expected shape:

```json
{
  "run_id": "483d2083455c",
  "requested_key_columns": ["Id"],
  "state": {
    "physical_dataframe_path": ".../483d2083455c_deduplicated.parquet",
    "current_dataset_version": "deduplication_v1",
    "current_step": "deduplication",
    "deduplication_result": {
      "applied_modes": [],
      "key_columns": ["Id"],
      "keep_strategy": "first",
      "before_row_count": 3337,
      "after_row_count": 3337,
      "dropped_row_count": 0,
      "full_row_duplicate_count": 0,
      "key_duplicate_count": 0,
      "duplicate_group_count": 0,
      "notes": [
        "Checked key-based duplicates on ['Id'] (source=execution_plan.columns); none were detected.",
        "No duplicate rows were detected; dataset was carried forward unchanged."
      ]
    }
  }
}
```

## How To Verify The Result

### Verify through API

Check:

- `state.deduplication_result.before_row_count`
- `state.deduplication_result.after_row_count`
- `state.deduplication_result.dropped_row_count`
- `state.physical_dataframe_path`

### Verify the output file exists

Expected current fallback output path pattern:

```text
.tmp/agentic-data-cleaner/outputs/{run_id}_deduplicated.parquet
```

### Verify with pandas locally

```powershell
@'
import pandas as pd

before_path = r"\tmp\agentic-data-cleaner\uploads\b2996a5d51ae43e6b17cd49ac9f65d4c.parquet"
after_path = r"D:\personal\hcmus\DoAnTotNghiep\Agentic-Data-Cleaner\.tmp\agentic-data-cleaner\outputs\483d2083455c_deduplicated.parquet"

before_df = pd.read_parquet(before_path)
after_df = pd.read_parquet(after_path)

print("before_rows =", len(before_df))
print("after_rows =", len(after_df))
print("before_full_dup =", int(before_df.duplicated().sum()))
print("after_full_dup =", int(after_df.duplicated().sum()))
print("after_id_dup =", int(after_df.duplicated(subset=['Id']).sum()))
'@ | .\.venv\Scripts\python -
```

Expected for the current sample:

- `before_rows = 3337`
- `after_rows = 3337`
- `before_full_dup = 0`
- `after_full_dup = 0`
- `after_id_dup = 0`

## Current Known Design Issues

### 1. `task_list` duplicates `execution_plan.task_list`

Status:

- known
- intentional for current graph routing
- not changed by the dedup debug endpoint

### 2. Windows storage path handling

Current behavior:

- configured `/tmp/.../outputs` path was not writable in this environment
- dedup worker now falls back to:

```text
.tmp/agentic-data-cleaner/outputs/
```

This is a runtime compatibility fix, not a new schema field.

### 3. LangGraph checkpoint type warnings

Current behavior:

- checkpoint deserialization logs warnings for custom types like `ExecutionPlan`, `StatisticalProfile`, and `DeduplicationResult`
- current functionality still works
- this is not a blocking issue for dedup endpoint testing

## Summary

The dedup debug path currently introduces one new typed result model and one new top-level state field that are actually required:

- `DeduplicationResult`
- `deduplication_result`

The public `GET /state` response has been narrowed so it only exposes dedup-relevant additional fields:

- `physical_dataframe_path`
- `worker_states`
- `validation_results`
- `deduplication_result`
- `current_dataset_version`

The main duplication that still exists in the typed state is:

- top-level `task_list`
- `execution_plan.task_list`

That duplication predates the current endpoint work and remains because the graph router depends on it.
