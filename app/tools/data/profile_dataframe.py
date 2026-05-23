"""Tool: compute comprehensive data quality statistics for a dataframe file."""
from pathlib import Path
from langchain_core.tools import tool
import pandas as pd


@tool
def profile_dataframe(file_path: str) -> dict:
    """Profile a data file — compute missing values, cardinality, and basic stats.

    Args:
        file_path: Path to a CSV, Excel, or Parquet file.

    Returns:
        dict with:
            - shape: [rows, cols]
            - columns: per-column stats (missing_count, missing_pct, dtype, unique_count, sample_values)
            - duplicate_rows: number of duplicate rows
    """
    # TODO: extend with outlier detection, distribution analysis
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        df = pd.read_csv(path)
    elif suffix in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    elif suffix == ".parquet":
        df = pd.read_parquet(path)
    else:
        raise ValueError(f"Unsupported format: {suffix}")

    column_stats = {}
    for col in df.columns:
        column_stats[col] = {
            "dtype": str(df[col].dtype),
            "missing_count": int(df[col].isna().sum()),
            "missing_pct": round(df[col].isna().mean() * 100, 2),
            "unique_count": int(df[col].nunique()),
            "sample_values": df[col].dropna().head(3).tolist(),
        }
    return {
        "shape": list(df.shape),
        "duplicate_rows": int(df.duplicated().sum()),
        "columns": column_stats,
    }
