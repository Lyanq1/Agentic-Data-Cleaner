"""Tool: remove duplicate rows from a data file."""
from pathlib import Path
from langchain_core.tools import tool
import pandas as pd


@tool
def remove_duplicates(
    file_path: str,
    subset: list[str] | None = None,
    keep: str = "first",
    output_path: str | None = None,
) -> dict:
    """Remove duplicate rows from a data file.

    Args:
        file_path: Path to input file.
        subset: Column names to consider. None means all columns.
        keep: "first" | "last" | False (drop all duplicates).
        output_path: Where to save the result. Defaults to overwriting input.

    Returns:
        dict with rows_before, rows_after, duplicates_removed, output_path.
    """
    path = Path(file_path)
    df = pd.read_csv(path) if path.suffix == ".csv" else pd.read_parquet(path)
    rows_before = len(df)
    df = df.drop_duplicates(subset=subset, keep=keep)  # type: ignore[arg-type]
    out = output_path or file_path
    if str(out).endswith(".csv"):
        df.to_csv(out, index=False)
    else:
        df.to_parquet(out, index=False)
    return {
        "rows_before": rows_before,
        "rows_after": len(df),
        "duplicates_removed": rows_before - len(df),
        "output_path": str(out),
    }
