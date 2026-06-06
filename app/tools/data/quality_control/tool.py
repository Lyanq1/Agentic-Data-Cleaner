import json
import pandas as pd
from langchain_core.tools import tool
from app.tools.data.quality_control.profiler import QualityProfiler

@tool
def perform_data_quality_check(file_path: str, null_threshold: float = 0.0) -> str:
    """Perform a Quality Control (QC) check on a dataset after processing.
    
    Args:
        file_path: Path to the dataset file (CSV, TSV, or Parquet).
        null_threshold: The fraction of nulls allowed in a column before it is flagged as an issue. Default 0.0 (any nulls will trigger an issue).
        
    Returns:
        A JSON string containing the QualityReport: number of duplicate rows, columns with nulls, disguised nulls, and any validation issues found.
    """
    profiler = QualityProfiler(null_threshold=null_threshold)
    report = profiler.check_file(file_path)
    
    return json.dumps(report.to_dict(), indent=2)

def perform_data_quality_check_df(df: pd.DataFrame, null_threshold: float = 0.0) -> str:
    """Helper to perform QC directly on a Pandas DataFrame."""
    profiler = QualityProfiler(null_threshold=null_threshold)
    report = profiler.check_dataframe(df)
    return json.dumps(report.to_dict(), indent=2)
