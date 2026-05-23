"""Tool: read a CSV, Excel, or Parquet file into a serializable dict."""
from pathlib import Path
from langchain_core.tools import tool
import pandas as pd


@tool
def read_file(file_path: str, max_rows: int = 1000) -> dict:
    """Read a data file (CSV, Excel, Parquet) and return its content as a dict.

    Args:
        file_path: Absolute or relative path to the data file.
        max_rows: Maximum number of rows to read (default 1000 for safety).

    Returns:
        dict with keys:
            - columns: list of column names
            - dtypes: dict mapping column name to dtype string
            - shape: [n_rows, n_cols]
            - sample: first 5 rows as list of dicts
            - total_rows: total row count in file
    """
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        df = pd.read_csv(path, nrows=max_rows)
        total = sum(1 for _ in open(path)) - 1  # approximate
    elif suffix in (".xlsx", ".xls"):
        df = pd.read_excel(path, nrows=max_rows)
        total = len(pd.read_excel(path, usecols=[0]))  # count rows
    elif suffix == ".parquet":
        df = pd.read_parquet(path).head(max_rows)
        total = len(pd.read_parquet(path, columns=[df.columns[0]]))
    else:
        raise ValueError(f"Unsupported file format: {suffix}")
    return {
        "columns": df.columns.tolist(),
        "dtypes": df.dtypes.astype(str).to_dict(),
        "shape": list(df.shape),
        "sample": df.head(5).to_dict(orient="records"),
        "total_rows": total,
    }
