"""Tool: save a dataframe to a file (CSV or Parquet)."""
from pathlib import Path
from langchain_core.tools import tool
import pandas as pd


@tool
def save_to_file(data: dict, output_path: str, format: str = "csv") -> dict:
    """Save agent result data to a file.

    Args:
        data: Dict with key "records" (list of row dicts) or "dataframe_path" (str path).
        output_path: Destination file path.
        format: "csv" | "parquet" | "json".

    Returns:
        dict with output_path and rows_written.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if "records" in data:
        df = pd.DataFrame(data["records"])
    elif "dataframe_path" in data:
        src = Path(data["dataframe_path"])
        df = pd.read_csv(src) if src.suffix == ".csv" else pd.read_parquet(src)
    else:
        raise ValueError("data must contain 'records' or 'dataframe_path'")
    if format == "csv":
        df.to_csv(out, index=False)
    elif format == "parquet":
        df.to_parquet(out, index=False)
    elif format == "json":
        df.to_json(out, orient="records", indent=2)
    return {"output_path": str(out), "rows_written": len(df)}
