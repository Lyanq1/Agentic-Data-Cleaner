"""Tool: handle missing values in a dataframe file."""
from pathlib import Path
from langchain_core.tools import tool
import pandas as pd


@tool
def clean_nulls(
    file_path: str,
    strategy: str = "drop",
    fill_value: str | None = None,
    output_path: str | None = None,
) -> dict:
    """Handle missing values in a data file.

    Args:
        file_path: Path to input file.
        strategy: "drop" | "fill" | "ffill" | "bfill".
        fill_value: Value to fill with when strategy="fill". Ignored otherwise.
        output_path: Where to save the result. Defaults to overwriting input.

    Returns:
        dict with rows_before, rows_after, nulls_removed, output_path.
    """
    # TODO: add per-column strategy support
    path = Path(file_path)
    df = pd.read_csv(path) if path.suffix == ".csv" else pd.read_parquet(path)
    rows_before = len(df)
    nulls_before = int(df.isna().sum().sum())

    if strategy == "drop":
        df = df.dropna()
    elif strategy == "fill" and fill_value is not None:
        df = df.fillna(fill_value)
    elif strategy == "ffill":
        df = df.ffill()
    elif strategy == "bfill":
        df = df.bfill()

    out = output_path or file_path
    if str(out).endswith(".csv"):
        df.to_csv(out, index=False)
    else:
        df.to_parquet(out, index=False)

    return {
        "rows_before": rows_before,
        "rows_after": len(df),
        "nulls_removed": nulls_before - int(df.isna().sum().sum()),
        "output_path": str(out),
    }
