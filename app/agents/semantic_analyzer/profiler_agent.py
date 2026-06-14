"""Combined Semantic Profiler Agent — single agent for columns, relationships, and validation."""
import json
import logging
import pandas as pd
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from app.agents.base import BaseAgent
from app.graphs.states.global_state import GlobalState
from app.graphs.states.profiles import SemanticProfile, ColumnSemanticProfileDetail
from app.agents.semantic_analyzer.prompts import COMBINED_PROFILER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

class ColumnSemanticProfileOutput(BaseModel):
    column_name: str = Field(description="Exact column name in the dataset.")
    description: str = Field(description="1-sentence clear description of the column's business meaning.")
    logical_group: str = Field(description="The semantic/logical group this column belongs to (e.g. 'Identity', 'Pricing', 'Address', 'Temporal').")
    relationships: List[str] = Field(
        default_factory=list,
        description="Cross-column relationships or functional dependencies (e.g. 'zip_code -> city', 'start_date < end_date')."
    )
    allow_missing: bool = Field(description="True if null values are logically acceptable from a business standpoint.")
    allow_missing_reason: str = Field(description="CoT reasoning explaining allow_missing.")
    expected_type: str = Field(description="Target semantic type: int | float | str | bool | date | datetime.")
    expected_type_reason: str = Field(description="CoT reasoning explaining target expected_type.")
    potential_dmv: List[str] = Field(
        default_factory=list,
        description="Disguised missing value placeholders found (e.g. 'N/A', 'null', 'none', '-', '0')."
    )
    potential_dmv_reason: str = Field(description="Reasoning explaining disguised missing values.")
    expected_str_pattern: Optional[str] = Field(default=None, description="Regex or string pattern description.")
    expected_str_pattern_reason: Optional[str] = Field(default=None, description="Reasoning explaining expected_str_pattern.")
    semantic_data_type: str = Field(description="The semantic data type of the column: Continuous | Discrete | Nominal | Ordinal | Temporal | Free text + Geospatial | Structured text | Boolean | Identifier.")
    fill_strategies: List[str] = Field(
        default_factory=list,
        description="Null-filling strategies applicable to this column based on its semantic data type."
    )
    
    # Integrated Quality Review / Audit
    is_error: bool = Field(description="True if actual statistics mismatch expectations (e.g. unexpected nulls, type mismatch, outliers).")
    error_types: List[str] = Field(
        default_factory=list,
        description="Subset of 'missing' | 'type_mismatch' | 'dmv' | 'string_outlier' | 'numeric_outlier'."
    )
    error_reason: Optional[str] = Field(default=None, description="Reasoning and explanation of the data quality issues found.")

class CombinedSemanticProfilerOutput(BaseModel):
    """Structured LLM output for the complete semantic profile."""
    table_summary: str = Field(description="A concise but detailed description of the table's overall business purpose.")
    thinking: str = Field(description="Detailed step-by-step Chain of Thought explaining the reasoning process behind column groupings, relationships, datatypes, DMVs, and quality audits.")
    columns: List[ColumnSemanticProfileOutput] = Field(default_factory=list)

class SemanticProfilerAgent(BaseAgent):
    """SemanticProfilerAgent performs complete combined semantic profiling and quality auditing in a single LLM pass."""

    name = "semantic_profiler"
    description = "Generates combined semantic profiles, relationships, and data quality audits."
    tools = []

    async def run(self, state: GlobalState) -> dict[str, Any]:
        statistical_profile = state.get("statistical_profile")
        dataset_path = state.get("dataset_path")

        if not statistical_profile:
            logger.error("SemanticProfilerAgent: no statistical_profile found in state.")
            return {"global_errors": "SemanticProfilerAgent: statistical_profile missing."}

        # 1. Read top 10 most popular (frequent) rows in the dataset
        try:
            if dataset_path.endswith(".parquet"):
                df = pd.read_parquet(dataset_path)
            else:
                df = pd.read_csv(dataset_path)
            
            # Find the top 10 most frequent (popular) unique row combinations
            # Exclude id columns from grouping to avoid uniqueness biasing popular counts
            group_cols = [c for c in df.columns if c not in {"id", "__id__"}]
            # Limit to at most 8 columns to avoid C-level tuple/integer overflow on Windows
            group_cols = group_cols[:8]
            try:
                if group_cols:
                    popular_rows = df[group_cols].astype(str).value_counts().head(10).reset_index()
                    if "count" in popular_rows.columns:
                        popular_rows = popular_rows.drop(columns=["count"])
                    elif 0 in popular_rows.columns:
                        popular_rows = popular_rows.drop(columns=[0])
                    
                    # Re-attach any columns that were not part of the grouping
                    for col in df.columns:
                        if col not in popular_rows.columns:
                            popular_rows[col] = df[col].head(len(popular_rows)).values
                    sample_df = popular_rows
                else:
                    sample_df = df.head(10)
            except Exception as inner_e:
                logger.warning(f"SemanticProfilerAgent: value_counts failed, falling back to head(10). Error: {inner_e}")
                sample_df = df.head(10)
                
            sample_text = sample_df.to_csv(index=False)
        except Exception as e:
            logger.error(f"SemanticProfilerAgent: failed to read top popular sample rows: {e}")
            sample_text = "Failed to load sample rows"


        # 2. Format statistical schema
        schema_info = []
        expected_columns = []
        for col_profile in statistical_profile.columns:
            expected_columns.append(col_profile.column_name)
            schema_info.append({
                "column_name": col_profile.column_name,
                "dtype": col_profile.dtype,
                "null_count": col_profile.null_count,
                "null_rate": col_profile.null_rate,
                "unique_count": col_profile.unique_count,
                "sample_values": col_profile.sample_values,
                "interpretation": col_profile.interpretation,
            })

        human_content = (
            f"## Dataset Statistical Profile\n```json\n{json.dumps(schema_info, indent=2)}\n```\n\n"
            f"## First 10 Sample Rows (CSV)\n```csv\n{sample_text}\n```\n"
        )

        messages = [
            SystemMessage(content=COMBINED_PROFILER_SYSTEM_PROMPT),
            HumanMessage(content=human_content),
        ]

        logger.info("SemanticProfilerAgent: invoking LLM for combined profile and quality review...")
        structured_llm = self.llm.with_structured_output(CombinedSemanticProfilerOutput)

        response = None
        attempt = 1
        last_hint = ""
        while attempt <= 3:
            if attempt > 1:
                logger.warning(f"SemanticProfilerAgent: Retry attempt {attempt} due to missing columns in LLM output.")
                messages.append(AIMessage(content=f"Attempt {attempt-1} failed. Let me correct that."))
                messages.append(HumanMessage(content=f"Error: {last_hint}\nPlease try again and make sure to include ALL columns: {expected_columns}"))

            try:
                response = await structured_llm.ainvoke(messages)
                returned_cols = {col.column_name for col in response.columns}
                missing = set(expected_columns) - returned_cols
                if not missing:
                    break
                else:
                    last_hint = f"The following columns were missing in your output: {list(missing)}"
            except Exception as e:
                logger.error(f"SemanticProfilerAgent: LLM invocation failed on attempt {attempt}: {e}")
                last_hint = f"LLM invocation failed: {e}"
            
            attempt += 1

        if not response:
            return {"global_errors": "SemanticProfilerAgent failed after 3 attempts."}

        # 3. Map to final SemanticProfile state model
        def map_fill_strategies(s_type: str) -> List[str]:
            dt = (s_type or "").strip().lower()
            if "continuous" in dt:
                return ["fill_mean", "fill_median"]
            elif "discrete" in dt:
                return ["fill_median", "fill_mode"]
            elif "nominal" in dt:
                return ["fill_mode", "fill_llm", "keep_null"]
            elif "ordinal" in dt:
                return ["fill_mode", "fill_median"]
            elif "temporal" in dt:
                return ["fill_median"]
            elif "free text" in dt or "geospatial" in dt or "geo" in dt:
                return ["fill_llm"]
            elif "structured text" in dt:
                return ["fill_llm", "drop_row"]
            elif "boolean" in dt:
                return ["fill_mode", "fill_constant"]
            elif "identifier" in dt:
                return ["drop_row"]
            else:
                return ["fill_mode", "fill_llm", "keep_null"]

        columns_dict: Dict[str, ColumnSemanticProfileDetail] = {}
        for col in response.columns:
            # Enforce strict mapping of fill strategies based on semantic_data_type
            strategies = col.fill_strategies or map_fill_strategies(col.semantic_data_type)
            columns_dict[col.column_name] = ColumnSemanticProfileDetail(
                description=col.description,
                logical_group=col.logical_group,
                relationships=col.relationships,
                allow_missing=col.allow_missing,
                allow_missing_reason=col.allow_missing_reason,
                expected_type=col.expected_type,
                expected_type_reason=col.expected_type_reason,
                potential_dmv=col.potential_dmv,
                potential_dmv_reason=col.potential_dmv_reason,
                expected_str_pattern=col.expected_str_pattern,
                expected_str_pattern_reason=col.expected_str_pattern_reason,
                is_error=col.is_error,
                error_types=col.error_types,
                error_reason=col.error_reason,
                semantic_data_type=col.semantic_data_type or "Nominal",
                fill_strategies=strategies,
            )

        # Fallback stubs for missing columns
        for col_name in expected_columns:
            if col_name not in columns_dict:
                columns_dict[col_name] = ColumnSemanticProfileDetail(
                    description="No description provided.",
                    logical_group="Unknown",
                    relationships=[],
                    allow_missing=True,
                    allow_missing_reason="Fallback.",
                    expected_type="str",
                    expected_type_reason="Fallback.",
                    is_error=False,
                    semantic_data_type="Nominal",
                    fill_strategies=["fill_mode", "fill_llm", "keep_null"],
                )

        final_profile = SemanticProfile(
            table_summary=response.table_summary,
            thinking=response.thinking,
            columns=columns_dict
        )

        logger.info("SemanticProfilerAgent completed profiling successfully.")
        return {
            "semantic_profile": final_profile,
            "current_step": "semantic_profile",
            "completed_steps": "semantic_profile"
        }
