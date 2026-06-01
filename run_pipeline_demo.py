import asyncio
import json
from pathlib import Path

from app.ingestion.normalizer import ingest_to_canonical
from app.services.pipeline import run_pipeline, get_pipeline_state

def get_val(obj, key, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)

async def main():
    # We will use the olist_order_reviews_dataset.csv dataset
    original_csv = Path("tests/olist_order_reviews_dataset.csv")
    if not original_csv.exists():
        print("Error: tests/olist_order_reviews_dataset.csv not found.")
        return
        
    print(f"--- 1. Ingesting raw dataset: {original_csv} ---")
    canonical_path, input_format, _ = ingest_to_canonical(original_csv)
    print(f"Canonical path generated: {canonical_path}")
    print(f"Original input format: {input_format.value}")

    print("\n--- 2. Executing LangGraph Data Cleansing Pipeline ---")
    run_id = "demo-run-hospital"
    
    # Run the pipeline
    await run_pipeline(
        run_id=run_id,
        canonical_path=str(canonical_path),
        input_format=input_format.value,
        user_prompt="Analyze the business context of this dataset, identify the logical column groups, detect any cross-column functional dependencies or relationships, detect potential disguised null values, and suggest appropriate cleaning strategies for the entire dataset.",
        original_filename="olist_order_reviews_dataset.csv"
    )
    
    # 3. Retrieve final state
    state = await get_pipeline_state(run_id)
    if not state:
        print("Failed to retrieve pipeline state.")
        return
        
    # 4. Display results beautifully
    print("\n" + "="*80)
    print("                      DEMO PIPELINE RUN COMPLETE")
    print("="*80)
    
    # Statistical Profile summary
    stat_prof = state.get("statistical_profile")
    if stat_prof:
        print(f"\n📊 [1. STATISTICAL EDA PROFILE]")
        print(f"   Source              : {get_val(stat_prof, 'source')}")
        print(f"   Total Rows          : {get_val(stat_prof, 'total_rows'):,}")
        print(f"   Total Columns       : {get_val(stat_prof, 'total_columns')}")
        print(f"   Duplicate Rows      : {get_val(stat_prof, 'duplicate_rows', 0):,}")
        print(f"   PK Candidates       : {get_val(stat_prof, 'pk_candidates')}")
        print(f"   Near-Unique Columns : {get_val(stat_prof, 'near_unique_columns')}")
        print(f"   Categorical Columns : {get_val(stat_prof, 'categorical_columns')}")
        print(f"   High-Null Columns   : {get_val(stat_prof, 'high_null_columns')}")
        
        # Detail per column
        print("\n   --- Columns Detail ---")
        columns = get_val(stat_prof, 'columns') or []
        for col in columns:
            col_name = get_val(col, 'column_name')
            print(f"     • Column: '{col_name}'")
            print(f"       - Dtype            : {get_val(col, 'dtype')}")
            print(f"       - Nulls            : {get_val(col, 'null_count'):,} / {get_val(stat_prof, 'total_rows'):,} ({get_val(col, 'null_rate'):.2%})")
            print(f"       - Uniqueness       : {get_val(col, 'unique_count'):,} distinct values (ratio: {get_val(col, 'unique_ratio'):.4f})")
            
            patterns = get_val(col, 'detected_patterns')
            if patterns:
                print(f"       - Detected Patterns: {patterns}")
                
            samples = get_val(col, 'sample_values')
            if samples:
                print(f"       - Sample Values    : {samples}")
                
            interpretation = get_val(col, 'interpretation')
            if interpretation:
                print(f"       - Interpretation   : {interpretation}")
                
            num_stats = get_val(col, 'numeric_stats')
            if num_stats:
                print(f"       - Numeric Stats    : avg={get_val(num_stats, 'avg')}, min={get_val(num_stats, 'min')}, max={get_val(num_stats, 'max')}, std={get_val(num_stats, 'std')}")
                
            cat_stats = get_val(col, 'categorical_stats')
            if cat_stats:
                freqs = get_val(cat_stats, 'frequencies') or []
                freq_desc = ", ".join(f"'{f.get('value')}': {f.get('count')} ({f.get('pct'):.1%})" for f in freqs[:3])
                print(f"       - Categorical Stats: {freq_desc}")
            print()
        
    # Semantic Profile summary
    semantic_prof = state.get("semantic_profile")
    if semantic_prof:
        print(f"\n🧠 [2. COMBINED SEMANTIC PROFILE]")
        print(f"   Table Summary: {get_val(semantic_prof, 'table_summary')}")
        print(f"   LLM Thinking (Chain of Thought):")
        thinking_text = get_val(semantic_prof, 'thinking', 'No thinking log provided.')
        # Wrap lines beautifully
        for line in thinking_text.split('\n'):
            print(f"     | {line}")
        print()
        
        # Group columns by logical group
        groups = {}
        columns_map = get_val(semantic_prof, 'columns') or {}
        for col_name, detail in columns_map.items():
            grp = get_val(detail, 'logical_group')
            groups.setdefault(grp, []).append(col_name)
            
        print("   Detected Logical Groups:")
        for grp, cols in groups.items():
            print(f"     - Group '{grp}': {cols}")
            
        print("\n   Detected Cross-Column Relationships:")
        relations_found = False
        for col_name, detail in columns_map.items():
            rels = get_val(detail, 'relationships')
            if rels:
                relations_found = True
                print(f"     - {col_name} -> {rels}")
        if not relations_found:
            print("     - No relations detected.")
            
        print("\n   Detailed Per-Column Semantic Profiles:")
        for col_name, detail in columns_map.items():
            print(f"     • Column: '{col_name}'")
            print(f"       - Description      : {get_val(detail, 'description')}")
            print(f"       - Logical Group    : {get_val(detail, 'logical_group')}")
            
            # Missing value policy
            allow_missing = get_val(detail, 'allow_missing')
            missing_reason = get_val(detail, 'allow_missing_reason')
            print(f"       - Allow Missing    : {allow_missing} (Reason: {missing_reason})" if missing_reason else f"       - Allow Missing    : {allow_missing}")
            
            # Expected Type
            exp_type = get_val(detail, 'expected_type')
            type_reason = get_val(detail, 'expected_type_reason')
            print(f"       - Expected Type    : {exp_type} (Reason: {type_reason})" if type_reason else f"       - Expected Type    : {exp_type}")
            
            # Expected Pattern
            pattern = get_val(detail, 'expected_str_pattern')
            pat_reason = get_val(detail, 'expected_str_pattern_reason')
            if pattern:
                print(f"       - Expected Pattern : '{pattern}' (Reason: {pat_reason})" if pat_reason else f"       - Expected Pattern : '{pattern}'")
                
            # Potential DMV (Disguised Missing Values)
            dmvs = get_val(detail, 'potential_dmv')
            dmv_reason = get_val(detail, 'potential_dmv_reason')
            if dmvs:
                print(f"       - Potential DMVs   : {dmvs} (Reason: {dmv_reason})" if dmv_reason else f"       - Potential DMVs   : {dmvs}")
                
            # Errors/Anomalies
            is_err = get_val(detail, 'is_error')
            if is_err:
                err_types = get_val(detail, 'error_types')
                err_reason = get_val(detail, 'error_reason')
                print(f"       - ⚠️ Quality Error : Types: {err_types} | Reason: {err_reason}")
            print()

    # Input Validation summary
    validation = state.get("input_validation_result")
    if validation:
        print(f"\n🛡️ [3. INPUT VALIDATION DECISION]")
        print(f"   Intent Description: {get_val(validation, 'intent_description')}")
        print("   Clarification Questions Proposed:")
        questions = get_val(validation, 'clarification_questions') or []
        for i, q in enumerate(questions, 1):
            print(f"     {i}. Question: {get_val(q, 'question')}")
            print(f"        Options: {get_val(q, 'options')}")
            
    print("\n" + "="*80)
    
    # Cleanup canonical parquet file
    if canonical_path.exists():
        canonical_path.unlink()

if __name__ == "__main__":
    import sys
    import selectors
    if sys.platform == 'win32':
        loop_factory = lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())
    else:
        loop_factory = None
    asyncio.run(main(), loop_factory=loop_factory)
