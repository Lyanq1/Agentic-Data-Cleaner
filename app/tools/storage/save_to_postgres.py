"""Tool: save a dataframe to a Postgres table."""
from langchain_core.tools import tool
from app.core.config import get_settings


@tool
def save_to_postgres(data: dict, table_name: str, if_exists: str = "append") -> dict:
    """Save agent result data to a Postgres table.

    Args:
        data: Dict with key "records" (list of row dicts) or "dataframe_path".
        table_name: Target table name in Postgres.
        if_exists: "append" | "replace" | "fail".

    Returns:
        dict with table_name and rows_written.

    Note:
        Uses a synchronous SQLAlchemy engine for pandas.to_sql compatibility.
        TODO: replace with async bulk insert for production scale.
    """
    import pandas as pd
    from pathlib import Path
    from sqlalchemy import create_engine
    settings = get_settings()
    # pandas.to_sql requires a sync engine (psycopg2 driver)
    sync_url = settings.postgres_url.replace("+asyncpg", "").replace("postgresql", "postgresql+psycopg2")
    engine = create_engine(sync_url)
    if "records" in data:
        df = pd.DataFrame(data["records"])
    elif "dataframe_path" in data:
        src = Path(data["dataframe_path"])
        df = pd.read_csv(src) if src.suffix == ".csv" else pd.read_parquet(src)
    else:
        raise ValueError("data must contain 'records' or 'dataframe_path'")
    df.to_sql(table_name, engine, if_exists=if_exists, index=False)
    engine.dispose()
    return {"table_name": table_name, "rows_written": len(df)}
