"""Tool: normalize column names and coerce data types."""
from pathlib import Path
from langchain_core.tools import tool
import pandas as pd
import re


@tool
def normalize_columns(
    file_path: str,
    output_path: str | None = None,
) -> dict:
    """Normalize column names to snake_case and coerce obvious type mismatches.

    Args:
        file_path: Path to input file.
        output_path: Where to save the result. Defaults to overwriting input.

    Returns:
        dict with renamed_columns mapping and output_path.
    """
    # TODO: add explicit dtype_map argument for forced type coercion
    path = Path(file_path)
    df = pd.read_csv(path) if path.suffix == ".csv" else pd.read_parquet(path)
    renamed = {}
    new_cols = []
    for col in df.columns:
        normalized = re.sub(r"[^\w]+", "_", col.strip().lower()).strip("_")
        renamed[col] = normalized
        new_cols.append(normalized)
    df.columns = new_cols
    df = df.infer_objects()
    out = output_path or file_path
    if str(out).endswith(".csv"):
        df.to_csv(out, index=False)
    else:
        df.to_parquet(out, index=False)
    return {"renamed_columns": renamed, "output_path": str(out)}
