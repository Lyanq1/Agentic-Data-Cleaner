from pathlib import Path
import pandas as pd
from langchain_core.tools import tool
from app.tools.data.eda.profiler import StatisticalProfiler

@tool
def perform_eda(file_path: str) -> dict:
    """Perform Statistical Profiling EDA on a dataset (CSV, TSV, or Parquet).
    Args:
        file_path: Path to the dataset file (CSV, TSV, or Parquet).

    Returns:
        A dictionary containing the full statistical report (nulls, uniqueness, string patterns, distributions).
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    profiler = StatisticalProfiler()
    if path.suffix.lower() == ".parquet":   
        report = profiler.profile_parquet(path)
    elif path.suffix.lower() in {".csv", ".tsv"}:
        sep = "\t" if path.suffix.lower() == ".tsv" else ","
        df = pd.read_csv(path, sep=sep)
        report = profiler.profile_dataframe(df, source=str(path))
    else:
        raise ValueError(f"Unsupported file format: {path.suffix}")

    return report.to_dict()
