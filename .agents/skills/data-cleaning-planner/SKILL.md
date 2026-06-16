---
name: data-cleaning-planner
description: How to generate, debug, or refine an execution plan for the Agentic-Data-Cleaner project. Make sure to use this skill whenever the user asks you to "create a cleaning plan", "replan the dataset", "debug the validator error and replan", or generally needs help formulating the JSON ExecutionPlan for data cleaning tasks (deduplication, null handling, type casting).
---

# Data Cleaning Planner

You are acting as the Senior AI Data Engineer and Pipeline Architect for the Agentic-Data-Cleaner system. Your job is to construct or refine a detailed cleaning Execution Plan conforming to a strict JSON schema based on the provided Dataset Statistical Profile, Semantic Profile, and Input Validation Decisions.

When the user asks you to write or debug a plan, follow these structured steps:

### STEP 1 — Context & Input Gathering

First, ensure you have the necessary context from the user. You need:
1. **Statistical Profile**: Tells you actual dtypes, null_count, unique_ratio, duplicate_rows.
2. **Semantic Profile**: Tells you expected_type, allow_missing, and potential disguised missing values.
3. **Input Validation Decision**: Contains strategies (e.g., fill with mean), resolutions, and user clarifications (e.g., "Use user_id as primary key").

If you are **REPLANNING** because a previous plan failed, you must also look for the `Validation Error` or `replan_hints`.

### STEP 2 — Detect Work Areas

Determine if cleaning is necessary for each of the three core steps:

1. **Deduplication (`dedup_agent`)**:
   - Check if `duplicate_rows > 0` or key identifier columns have `unique_ratio < 1.0`.
   - If none, set `skip = true` and provide a `skip_reason`.

2. **Null Handling (`null_agent`)**:
   - Check if any column has `null_count > 0`, `null_rate > 0`, or contains `potential_dmv` (disguised missing values).
   - If none, set `skip = true` and provide a `skip_reason`.

3. **Type Casting (`typecast_agent`)**:
   - Compare physical `dtype` with semantic `expected_type`.
   - If they match perfectly, set `skip = true`. Otherwise, don't skip.

### STEP 3 — Construct Strategies

For each active task, construct the strategy:

- **Deduplication Strategy**: 
  - `dedup_scope`: "row_level", "key_level", or "entity_level"
  - `primary_keys`: e.g. `["customer_id"]`
  - `duplicate_types`: e.g. `["exact_row", "duplicate_key"]`
  - `exact_match`, `key_based`, `fuzzy_matching`, `llm_review` configurations.
  - Make sure to map any user answers (like "Use user_id") into `primary_keys` and `key_based.keys`.

- **Null Handling Strategy**:
  - `per_column`: Map each column to a strategy: `fill_mean`, `fill_median`, `fill_mode`, `fill_value`, `fill_llm`, `drop_row`, `drop_column`, or `leave_as_is`.
  - **CRITICAL**: Never use `fill_mean` or `fill_median` on non-numeric types (e.g., string/object). Use `fill_mode`, `fill_value`, or `drop_row` instead.
  - If `allow_missing = true` for a column, use `leave_as_is`.

- **Type Casting Strategy**:
  - `per_column`: Map each column to its `expected_type` ("int", "float", "str", "bool", "date", "datetime") and optional `parse_format`.

### STEP 4 — Define Verification & Failure Policy

- Set `validation_scope: "post_task"` and `validator_mode: "pandas_custom"`.
- Define `checks` (e.g., `column_unique`, `null_rate_lte`, `dataframe_no_exact_duplicates`).
- `failure_policy` must have `"after_max_retries": "replan"`.

### STEP 5 — HANDLING REPLAN & RECOVERY

If the user is asking you to **replan** due to an output validation failure:
- **Read the Hints**: Listen to what the validator complained about.
- **Adjust Parameters**: 
  - If deduplication dropped too many rows, reduce the scope, change `primary_keys`, or relax exact matching. 
  - If type casting failed, check if you need to use `parse_format` or drop unparseable rows prior to this step.
  - If null handling failed a `null_rate_lte` check, ensure you aren't leaving nulls as-is (`leave_as_is`) for columns that require no nulls.
- **Update Rationale**: Explicitly state how you changed the plan to address the failure in the `rationale` field of the failing task. Do not generate the exact same plan again!

### STEP 6 — OUTPUT JSON SCHEMA FORMAT

Your final output must be a valid JSON object matching the `ExecutionPlan` structure. Do not invent new fields.
