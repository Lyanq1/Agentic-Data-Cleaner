import logging
import pandas as pd
from typing import Any

logger = logging.getLogger(__name__)

def resolve_benchmark_clarifications(state: Any, val_result: dict) -> dict:
    """Auto-resolves clarification questions in benchmark mode using the ground truth dataset."""
    import copy
    resolved = copy.deepcopy(val_result)
    
    dirty_path = state.get("dataset_path")
    gt_path = state.get("ground_truth_path")
    
    if not dirty_path or not gt_path:
        logger.warning("resolve_benchmark_clarifications: Missing dataset_path or ground_truth_path in state.")
        resolved["status"] = "ready"
        return resolved
        
    try:
        if str(dirty_path).endswith(".parquet"):
            dirty_df = pd.read_parquet(dirty_path)
        else:
            dirty_df = pd.read_csv(dirty_path)
            
        if str(gt_path).endswith(".parquet"):
            gt_df = pd.read_parquet(gt_path)
        else:
            gt_df = pd.read_csv(gt_path)
    except Exception as e:
        logger.error(f"resolve_benchmark_clarifications: Failed to load datasets: {e}")
        resolved["status"] = "ready"
        return resolved

    clarifications = resolved.get("clarifications") or {}
    resolved_by_user = []
    
    action_plans = {
        "null": [],
        "duplicate": [],
        "typecast": []
    }
    
    # 1. Resolve NULL clarifications
    null_clars = clarifications.get("null") or {}
    for q_key, q_val in list(null_clars.items()):
        if not isinstance(q_val, dict):
            continue
            
        if q_key.startswith("Q1_allow_missing_column_"):
            col_name = q_key[len("Q1_allow_missing_column_"):]
            if col_name in gt_df.columns:
                has_nulls_in_gt = gt_df[col_name].isna().any()
                q_val["answer"] = "Yes" if has_nulls_in_gt else "No"
            else:
                q_val["answer"] = "No"
            resolved_by_user.append(f"null_allow_missing_{col_name}")
            action_plans["null"].append(f"Column '{col_name}' allow_missing set to {q_val['answer']}")
            
        elif q_key.startswith("Q2_strategy_column_"):
            col_name = q_key[len("Q2_strategy_column_"):]
            options = q_val.get("options") or []
            
            strategy = "keep_null"
            fill_val = None
            
            if col_name not in gt_df.columns:
                strategy = "drop_row"
            elif col_name not in dirty_df.columns:
                strategy = "keep_null"
            else:
                dirty_col = dirty_df[col_name]
                gt_col = gt_df[col_name]
                
                null_mask = dirty_col.isna()
                null_indices = dirty_df.index[null_mask]
                
                if len(null_indices) > 0:
                    if len(dirty_df) == len(gt_df):
                        null_gt_values = gt_col.iloc[null_indices]
                        if null_gt_values.isna().all():
                            strategy = "keep_null"
                        else:
                            filled_vals = null_gt_values.dropna()
                            if not filled_vals.empty:
                                most_common = filled_vals.mode().iloc[0] if not filled_vals.mode().empty else filled_vals.iloc[0]
                                
                                dirty_numeric = pd.to_numeric(dirty_col, errors="coerce")
                                dirty_mean = dirty_numeric.mean()
                                dirty_median = dirty_numeric.median()
                                dirty_mode_series = dirty_col.mode()
                                dirty_mode = dirty_mode_series.iloc[0] if not dirty_mode_series.empty else None
                                
                                import math
                                try:
                                    is_mean = not pd.isna(dirty_mean) and (math.isclose(float(most_common), float(dirty_mean), rel_tol=1e-3) or round(float(dirty_mean)) == int(most_common))
                                except Exception:
                                    is_mean = False
                                    
                                try:
                                    is_median = not pd.isna(dirty_median) and (math.isclose(float(most_common), float(dirty_median), rel_tol=1e-3) or round(float(dirty_median)) == int(most_common))
                                except Exception:
                                    is_median = False
                                    
                                try:
                                    is_mode = dirty_mode is not None and str(most_common) == str(dirty_mode)
                                except Exception:
                                    is_mode = False
                                    
                                if is_mean and "fill_mean" in options:
                                    strategy = "fill_mean"
                                    fill_val = most_common
                                elif is_median and "fill_median" in options:
                                    strategy = "fill_median"
                                    fill_val = most_common
                                elif is_mode and "fill_mode" in options:
                                    strategy = "fill_mode"
                                    fill_val = most_common
                                else:
                                    strategy = "fill_value"
                                    fill_val = most_common
                            else:
                                strategy = "keep_null"
                    else:
                        common_cols = [c for c in dirty_df.columns if c in gt_df.columns and not dirty_df[c].isna().any() and not gt_df[c].isna().any()]
                        if common_cols:
                            dirty_null_rows = dirty_df[null_mask]
                            match_keys = common_cols[:3]
                            merged = pd.merge(dirty_null_rows[match_keys], gt_df, on=match_keys, how='inner')
                            if len(merged) < len(dirty_null_rows) * 0.5:
                                strategy = "drop_row"
                            else:
                                gt_values = merged[col_name]
                                if gt_values.isna().all():
                                    strategy = "keep_null"
                                else:
                                    non_nulls = gt_values.dropna()
                                    if not non_nulls.empty:
                                        most_common = non_nulls.mode().iloc[0] if not non_nulls.mode().empty else non_nulls.iloc[0]
                                        strategy = "fill_value"
                                        fill_val = most_common
                        else:
                            strategy = "drop_row"
                            
            matched_option = None
            for opt in options:
                if opt.lower().startswith(strategy):
                    matched_option = opt
                    break
            
            if matched_option is None:
                if strategy == "fill_value" and fill_val is not None:
                    for opt in options:
                        if "fill_value" in opt or "custom" in opt.lower():
                            matched_option = f"fill_value: {fill_val}"
                            break
                if matched_option is None:
                    matched_option = options[0] if options else "keep_null"
            else:
                if strategy == "fill_value" and fill_val is not None:
                    matched_option = f"fill_value: {fill_val}"
                    
            q_val["answer"] = matched_option
            resolved_by_user.append(f"null_strategy_{col_name}")
            action_plans["null"].append(f"Impute column '{col_name}' using strategy '{matched_option}'")
            
        elif q_key.startswith("Q3_semantic_insight") or q_key.startswith("Q4_semantic_insight"):
            q_val["answer"] = "Yes"
            resolved_by_user.append("null_semantic_insight")
            action_plans["null"].append("Null semantic insight confirmed.")

    # 2. Resolve DUPLICATE clarifications
    dup_clars = clarifications.get("duplicate") or {}
    for q_key, q_val in list(dup_clars.items()):
        if not isinstance(q_val, dict):
            continue
            
        if q_key == "Q1_strategy":
            options = q_val.get("options") or []
            recommended_opt = None
            for opt in options:
                if "(Recommended)" in opt:
                    recommended_opt = opt
                    break
            if recommended_opt:
                import re
                match = re.search(r"'(.*?)'", recommended_opt)
                if match:
                    col_name = match.group(1)
                    if col_name in gt_df.columns and gt_df[col_name].is_unique:
                        q_val["answer"] = recommended_opt
                    else:
                        exact_opt = None
                        for opt in options:
                            if "exact" in opt.lower() or "Option C" in opt:
                                exact_opt = opt
                                break
                        q_val["answer"] = exact_opt or recommended_opt
                else:
                    q_val["answer"] = recommended_opt
            else:
                q_val["answer"] = options[0] if options else "Option A"
            resolved_by_user.append("duplicate_strategy")
            action_plans["duplicate"].append(f"Deduplication strategy: {q_val['answer']}")
            
        elif q_key.startswith("Q2_semantic_insight") or q_key.startswith("Q3_semantic_insight"):
            q_val["answer"] = "Yes"
            resolved_by_user.append("duplicate_semantic_insight")
            action_plans["duplicate"].append("Duplicate semantic insight confirmed.")

    # 3. Resolve TYPECAST clarifications
    typecast_clars = clarifications.get("typecast") or {}
    for q_key, q_val in list(typecast_clars.items()):
        if not isinstance(q_val, dict):
            continue
            
        if q_key.startswith("Q1_cast_column_"):
            col_name = q_key[len("Q1_cast_column_"):]
            q_val["answer"] = "Yes"
            resolved_by_user.append(f"typecast_cast_{col_name}")
            action_plans["typecast"].append(f"Cast column '{col_name}' to expected type")
            
        elif q_key.startswith("Q2_semantic_insight") or q_key.startswith("Q3_semantic_insight"):
            q_val["answer"] = "Yes"
            resolved_by_user.append("typecast_semantic_insight")
            action_plans["typecast"].append("Typecast semantic insight confirmed.")

    resolved["status"] = "ready"
    resolved["resolved_by_user"] = resolved_by_user
    resolved["action_plan"] = {
        "null": " | ".join(action_plans["null"]) if action_plans["null"] else "None",
        "duplicate": " | ".join(action_plans["duplicate"]) if action_plans["duplicate"] else "None",
        "typecast": " | ".join(action_plans["typecast"]) if action_plans["typecast"] else "None"
    }
    
    return resolved
