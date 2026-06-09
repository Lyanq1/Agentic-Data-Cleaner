"""Node functions for the LangGraph pipeline."""

import logging
from datetime import UTC, datetime
from typing import Any, Literal, cast

from app.agents.deduplication.agent import DeduplicationAgent
from app.agents.input_validator.agent import InputValidatorAgent
from app.agents.null_agent.agent import NullAgent
from app.agents.semantic_analyzer.profiler_agent import SemanticProfilerAgent
from app.graphs.states.global_state import GlobalState
from app.graphs.states.output_validation import ValidationResultItem
from app.tools.data.eda import perform_eda
from app.graphs.utils import _resolve_active_task
from app.graphs.states.profiler_state import StatisticalProfile

logger = logging.getLogger(__name__)


# Data profiling node (runs statistical EDA on the uploaded dataset)
async def profiler_node(state: GlobalState) -> dict[str, Any]:
    """Run statistical EDA on the uploaded dataset.

    Reads ``dataset_path`` from state, calls ``perform_eda``, and writes
    the result into ``data_profile``.
    """
    if state.get("statistical_profile"):
        logger.info("profiler_node: Statistical profile already exists in state, skipping.")
        return {}

    dataset_path = state.get("dataset_path")
    if not dataset_path:
        logger.error("profiler_node: dataset_path is missing from state.")
        return {
            "global_errors": "profiler_node: dataset_path is missing from state.",
        }

    logger.info(f"profiler_node: profiling dataset at {dataset_path}")
    try:
        # perform_eda is a @tool — call .invoke() to get the dict result
        profile: dict[str, Any] = perform_eda.invoke({"file_path": dataset_path})
        validated_profile = StatisticalProfile.model_validate(profile)
    except Exception as e:
        logger.error(f"profiler_node: EDA failed — {e}")
        return {
            "global_errors": f"profiler_node: EDA failed — {e}",
        }

    logger.info(
        f"profiler_node: profiling complete — "
        f"{profile.get('total_rows', '?')} rows × {profile.get('total_columns', '?')} cols"
    )
    return {
        "statistical_profile": validated_profile,
        "current_step": "profiling",
        "completed_steps": "profiling",
    }


async def semantic_profile_node(state: GlobalState) -> dict[str, Any]:
    """Profile detailed semantic properties of the dataset columns by logical group."""
    if state.get("semantic_profile"):
        logger.info("semantic_profile_node: Semantic profile already exists in state, skipping.")
        return {}
    agent = SemanticProfilerAgent()
    return await agent.run(state)


# Input validation node (analyzes data profile and reports validation status)
async def input_validator_node(state: GlobalState) -> dict[str, Any]:
    """Invoke the InputValidatorAgent to analyze the EDA profile via LLM."""

    agent = InputValidatorAgent()
    result = await agent.run(state)

    return {
        **result,
        "current_step": "input_validation",
        "completed_steps": "input_validation",
    }


# Planner node (Đề xuất kế hoạch làm sạch động)
async def planner_node(state: GlobalState) -> dict[str, Any]:
    """Invoke the PlannerAgent to generate the cleaning plan and task list."""
    logger.info("planner_node: Generating cleaning plan and DAG task list...")
    from app.agents.planner.agent import PlannerAgent

    agent = PlannerAgent()
    result = await agent.run(state)

    return {
        **result,
        "current_step": "planning",
        "completed_steps": "planning",
    }

# Deduplication Worker stub node
async def dedup_agent_node(state: GlobalState) -> dict[str, Any]:
    """Run the deterministic simple-case deduplication worker."""
    logger.info("dedup_agent_node: Executing dataset deduplication checks...")
    agent = DeduplicationAgent()
    result = await agent.run(state)

    return {
        **result,
        "current_step": "deduplication",
        "completed_steps": "deduplication",
    }


# Null Handling Worker node
async def null_agent_node(state: GlobalState) -> dict[str, Any]:
    """Run the Null Agent: drops rows with null in non-nullable columns (drop_row strategy)."""
    logger.info("null_agent_node: Processing missing values in dataset...")
    agent = NullAgent()
    result = await agent.run(state)

    return {
        **result,
        "current_step": "null_handling",
        "completed_steps": "null_handling",
    }


# Type Casting Worker stub node
async def type_agent_node(state: GlobalState) -> dict[str, Any]:
    """Skeletal Type Casting Worker."""
    logger.info("type_agent_node: Applying strict type cast constraints...")
    return _persist_passthrough_worker_version(state, "typecast_agent", "type_casting")


def _persist_passthrough_worker_version(
    state: GlobalState,
    agent_name: str,
    step_name: str,
) -> dict[str, Any]:
    """Worker stub contract: load latest lineage dataframe and save a new version to a temporary file.

    Real workers should replace the pass-through dataframe with their transformed
    dataframe, then keep the same append/version state update behavior.
    """
    import uuid
    from pathlib import Path
    from app.graphs.utils import _load_latest_dataframe, _resolve_active_task
    
    base_update: dict[str, Any] = {
        "current_step": step_name,
        "completed_steps": step_name,
    }

    try:
        task = _resolve_active_task(state)
        # Load the latest dataframe to pass through
        dataframe = _load_latest_dataframe(state, task) if task else None
        if dataframe is None or dataframe.empty:
            logger.warning(
                "%s: latest lineage dataframe is empty or missing; skipping version append.", agent_name
            )
            return base_update

        # Save to temporary parquet file
        file_id = state.get("project_id") or uuid.uuid4().hex[:12]
        output_dir = Path.cwd() / ".tmp" / "agentic-data-cleaner" / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = output_dir / f"{file_id}_{step_name}_temp.parquet"
        dataframe.to_parquet(output_path, index=False)
        
    except Exception as exc:
        logger.error("%s: failed to save temporary dataset: %s", agent_name, exc)
        return {
            **base_update,
            "global_errors": f"{agent_name}: failed to save temporary dataset: {exc}",
        }

    return {
        **base_update,
        "physical_dataframe_path": str(output_path),
    }


# Self-Correction Validator node
async def validator_node(state: GlobalState) -> dict[str, Any]:
    """Validate the active worker output using ValidatorAgent (LLM)."""
    from app.agents.result_validators.agent import ValidatorAgent
    from app.services.lineage_service import LineageService
    from app.services.lineage_utils import resolve_lineage_session_id

    current_idx = state.get("current_task_idx") or 0
    retry_count = state.get("retry_count") or 0
    active_task = _resolve_active_task(state)
    task_id = active_task.task_id if active_task else "unknown"
    agent_name = getattr(active_task.agent, "value", str(active_task.agent)) if active_task else "unknown"
    
    agent = ValidatorAgent()
    result = await agent.run(state)
    
    if not result.get("success"):
        logger.error("validator_node: ValidatorAgent failed to execute.")
        return {"global_errors": "ValidatorAgent failed to execute."}
        
    validator_result = result.get("validator_agent_result")
    df_validated_path = result.get("df_validated_path")
    
    passed = validator_result.passed if validator_result else False
    
    if passed:
        logger.info(f"validator_node: task '{task_id}' PASSED validation.")
        
        # Persist to LineageService since it passed
        session_id = resolve_lineage_session_id(state)
        new_version_str = state.get("current_dataset_version")
        if session_id and df_validated_path is not None:
            try:
                new_version = LineageService.append_new_version_from_file(
                    session_id=session_id,
                    file_path=df_validated_path,
                    agent_name=agent_name,
                    description=f"Output from {task_id} approved by ValidatorAgent."
                )
                new_version_str = str(new_version)
                logger.info(f"validator_node: dataset persisted as version {new_version_str}")
            except Exception as e:
                logger.error(f"validator_node: failed to persist to lineage: {e}")

        validation_item = ValidationResultItem(
            agent=agent_name,
            task_id=task_id,
            passed=True,
            failed_rules=[],
            recommended_next_action="pass",
            timestamp=datetime.now(UTC).isoformat(),
        )
        return {
            "current_task_idx": current_idx + 1,
            "retry_count": 0,
            "last_validation_error": None,
            "failed_task_id": None,
            "replan_reason": None,
            "next_node": None,
            "validation_results": validation_item,
            "dataset_version": new_version_str,
            "current_dataset_version": new_version_str,
            "current_step": "validation",
            "completed_steps": "validation",
        }

    # If Failed
    retry_count += 1
    max_retries = _max_retries_per_task(state)
    failed_rules = validator_result.failed_rules if validator_result else ["validator_rejected"]
    error_log = f"Failed Rules: {failed_rules}. Reasoning: {validator_result.reasoning if validator_result else ''}"
    
    recommended_next_action = "retry_worker"
    if retry_count >= max_retries:
        recommended_next_action = "replan"
        
    validation_item = ValidationResultItem(
        agent=agent_name,
        task_id=task_id,
        passed=False,
        failed_rules=failed_rules,
        recommended_next_action=cast(Any, recommended_next_action),
        replan_hints=validator_result.replan_hints if validator_result else {},
        timestamp=datetime.now(UTC).isoformat(),
    )

    if recommended_next_action == "replan":
        logger.warning(
            "validator_node: task '%s' failed validation. Action: %s. Routing to planner.",
            task_id,
            recommended_next_action,
        )
        return {
            "retry_count": retry_count,
            "last_validation_error": error_log,
            "failed_task_id": task_id,
            "replan_reason": f"Validation failed with policy action '{recommended_next_action}'. Errors: {failed_rules}",
            "next_node": "planner",
            "validation_results": validation_item,
            "global_errors": error_log,
            "current_step": "validation_failed",
        }

    logger.warning(
        "validator_node: task '%s' failed validation; retry %s/%s. Action: %s.",
        task_id,
        retry_count,
        max_retries,
        recommended_next_action,
    )
    return {
        "retry_count": retry_count,
        "last_validation_error": error_log,
        "failed_task_id": task_id,
        "next_node": None,
        "validation_results": validation_item,
        "current_step": "validation_failed",
    }


def _max_retries_per_task(state: GlobalState) -> int:
    plan = state.get("execution_plan")
    if plan is None:
        return 3
    constraints = (
        plan.get("global_constraints") if isinstance(plan, dict) else plan.global_constraints
    )
    if constraints is None:
        return 3
    value = (
        constraints.get("max_retries_per_task")
        if isinstance(constraints, dict)
        else constraints.max_retries_per_task
    )
    return int(value or 3)


# Final Report Generator node
async def report_agent_node(state: GlobalState) -> dict[str, Any]:
    """Skeletal Report Node — aggregates execution outcomes.
    Calculates cell-level F1-score evaluation metrics against Ground Truth for hospital dataset.
    """
    logger.info("report_agent_node: Summarizing transformations and token metrics...")
    
    import pandas as pd
    import numpy as np
    from pathlib import Path
    from app.services.lineage_service import LineageService
    from app.services.lineage_utils import resolve_lineage_session_id
    from app.graphs.utils import _load_dataframe

    # Load cleaned data
    cleaned_df = None
    session_id = resolve_lineage_session_id(state)
    if session_id:
        try:
            cleaned_df = LineageService.get_latest_version(session_id)
        except Exception as exc:
            logger.error(f"report_agent_node: failed to fetch latest version from lineage: {exc}")
            
    if cleaned_df is None or cleaned_df.empty:
        # Fallback to physical_dataframe_path or dataset_path
        for key in ["physical_dataframe_path", "dataset_path"]:
            path = state.get(key)
            if path:
                try:
                    cleaned_df = _load_dataframe(path)
                    break
                except Exception:
                    pass

    # Load original dirty data
    dirty_df = None
    dirty_path = state.get("dataset_path")
    if dirty_path:
        try:
            dirty_df = _load_dataframe(dirty_path)
        except Exception as exc:
            logger.error(f"report_agent_node: failed to load dirty dataframe: {exc}")

    # Check if the dataset matches the hospital dataset based on columns
    f1_metrics = None
    hospital_cols = {"ProviderNumber", "HospitalName", "MeasureCode", "MeasureName", "Stateavg"}
    if cleaned_df is not None and not cleaned_df.empty:
        matching_cols = [c for c in hospital_cols if c in cleaned_df.columns]
        if len(matching_cols) >= 3:
            # Matches hospital dataset! Perform evaluation against tests/hospital_clean.csv
            gt_path = Path.cwd() / "tests" / "hospital_clean.csv"
            if gt_path.exists() and dirty_df is not None and not dirty_df.empty:
                try:
                    logger.info(f"report_agent_node: hospital dataset detected, loading ground truth from {gt_path}")
                    gt_df = pd.read_csv(gt_path)
                    
                    # Align columns (exclude 'index' metadata column from GT)
                    gt_cols = [c for c in gt_df.columns if c != "index"]
                    common_cols = [c for c in gt_cols if c in cleaned_df.columns and c in dirty_df.columns]
                    
                    if common_cols:
                        # Align rows (ensure equal lengths by slicing to the minimum)
                        num_rows = min(len(gt_df), len(cleaned_df), len(dirty_df))
                        df_gt_aligned = gt_df.iloc[:num_rows][common_cols]
                        df_dirty_aligned = dirty_df.iloc[:num_rows][common_cols]
                        df_cleaned_aligned = cleaned_df.iloc[:num_rows][common_cols]
                        
                        total_cells = num_rows * len(common_cols)
                        total_tp = 0
                        total_fp = 0
                        total_fn = 0
                        total_correct = 0
                        
                        def get_equivalent_mask(s1: pd.Series, s2: pd.Series) -> pd.Series:
                            def normalize(s):
                                return s.astype(str).str.strip().str.lower().str.replace(r'\.0$', '', regex=True).replace({
                                    "nan": "__null__",
                                    "none": "__null__",
                                    "": "__null__",
                                    "empty": "__null__"
                                })
                            return normalize(s1) == normalize(s2)
                        
                        for col in common_cols:
                            is_gt_equal_dirty = get_equivalent_mask(df_gt_aligned[col], df_dirty_aligned[col])
                            is_cleaned_equal_gt = get_equivalent_mask(df_cleaned_aligned[col], df_gt_aligned[col])
                            is_cleaned_equal_dirty = get_equivalent_mask(df_cleaned_aligned[col], df_dirty_aligned[col])
                            
                            tp = ((~is_gt_equal_dirty) & is_cleaned_equal_gt).sum()
                            fp = ((~is_cleaned_equal_gt) & (~is_cleaned_equal_dirty)).sum()
                            fn = ((~is_gt_equal_dirty) & (~is_cleaned_equal_gt)).sum()
                            correct = is_cleaned_equal_gt.sum()
                            
                            total_tp += int(tp)
                            total_fp += int(fp)
                            total_fn += int(fn)
                            total_correct += int(correct)
                        
                        precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 1.0
                        recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 1.0
                        f1_score = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
                        accuracy = total_correct / total_cells
                        
                        f1_metrics = {
                            "cell_accuracy": round(accuracy, 4),
                            "error_correction_precision": round(precision, 4),
                            "error_correction_recall": round(recall, 4),
                            "f1_score": round(f1_score, 4),
                            "total_cells_evaluated": total_cells,
                            "tp": total_tp,
                            "fp": total_fp,
                            "fn": total_fn,
                        }
                        logger.info(f"report_agent_node: F1 evaluation complete: F1={f1_score:.4f}, Accuracy={accuracy:.4f}")
                except Exception as exc:
                    logger.error(f"report_agent_node: failed to evaluate F1 metrics: {exc}")
            else:
                logger.warning(f"report_agent_node: hospital dataset detected but ground truth file or dirty file not found (gt_path={gt_path})")

    return {
        "current_step": "reporting",
        "completed_steps": "reporting",
        "f1_metrics": f1_metrics,
    }

