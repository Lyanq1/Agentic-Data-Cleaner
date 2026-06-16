import uuid
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import SessionLocal
from app.models.lineage import LineageVersion, DatasetRecord

class LineageService:
    @staticmethod
    def append_new_version(
        session_id: uuid.UUID,
        df: pd.DataFrame,
        agent_name: str,
        description: str = ""
    ) -> int:
        """Appends a new version of the dataframe to the lineage records.
        
        Args:
            session_id: The UUID of the current dataset session.
            df: The new processed pandas DataFrame to save.
            agent_name: Name of the agent saving the data (e.g., "cleaner_agent").
            description: Description of the changes made.
            
        Returns:
            The new version number.
        """
        db: Session = SessionLocal()
        try:
            # 1. Determine the latest version
            current_max_version = db.query(func.max(LineageVersion.version)).filter(
                LineageVersion.session_id == session_id
            ).scalar()
            
            new_version = (current_max_version or 0) + 1
            
            # 2. Create a new LineageVersion entry
            db_version = LineageVersion(
                session_id=session_id,
                version=new_version,
                agent_name=agent_name,
                description=description
            )
            db.add(db_version)
            
            # Flush to database so the version row exists
            db.flush()
            
            # 3. Insert new dataset records
            records_dict = [
                {key: _json_safe_value(value) for key, value in row.items()}
                for row in df.to_dict(orient="records")
            ]
            db_records = [
                DatasetRecord(
                    session_id=session_id,
                    version=new_version,
                    data=row,
                    row_index=i
                )
                for i, row in enumerate(records_dict)
            ]
            
            db.bulk_save_objects(db_records)
            db.commit()
            
            return new_version
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()
            
    @staticmethod
    def append_new_version_from_file(
        session_id: uuid.UUID,
        file_path: str,
        agent_name: str,
        description: str = ""
    ) -> int:
        """Appends a new version from a file path (CSV or Parquet) using chunks to prevent OOM."""
        db: Session = SessionLocal()
        try:
            # 1. Determine the latest version
            current_max_version = db.query(func.max(LineageVersion.version)).filter(
                LineageVersion.session_id == session_id
            ).scalar()
            
            new_version = (current_max_version or 0) + 1
            
            # 2. Create a new LineageVersion entry
            db_version = LineageVersion(
                session_id=session_id,
                version=new_version,
                agent_name=agent_name,
                description=description
            )
            db.add(db_version)
            db.flush()
            
            # 3. Read file in chunks to avoid OOM
            import pandas as pd
            if str(file_path).endswith('.parquet'):
                import pyarrow.parquet as pq
                parquet_file = pq.ParquetFile(file_path)
                row_idx = 0
                for batch in parquet_file.iter_batches(batch_size=10000):
                    df_chunk = batch.to_pandas()
                    records_dict = [
                        {"session_id": session_id, "version": new_version, "data": {k: _json_safe_value(v) for k, v in row.items()}, "row_index": i}
                        for i, row in enumerate(df_chunk.to_dict(orient="records"), start=row_idx)
                    ]
                    db.bulk_insert_mappings(DatasetRecord, records_dict)
                    row_idx += len(df_chunk)
            else:
                chunk_iterator = pd.read_csv(file_path, chunksize=10000)
                row_idx = 0
                for df_chunk in chunk_iterator:
                    records_dict = [
                        {"session_id": session_id, "version": new_version, "data": {k: _json_safe_value(v) for k, v in row.items()}, "row_index": i}
                        for i, row in enumerate(df_chunk.to_dict(orient="records"), start=row_idx)
                    ]
                    db.bulk_insert_mappings(DatasetRecord, records_dict)
                    row_idx += len(df_chunk)
            
            db.commit()
            return new_version
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    @staticmethod
    def get_latest_version(session_id: uuid.UUID) -> pd.DataFrame:
        """Retrieves the latest version of the dataset as a Pandas DataFrame."""
        db: Session = SessionLocal()
        try:
            # 1. Get the latest version number
            latest_version = db.query(func.max(LineageVersion.version)).filter(
                LineageVersion.session_id == session_id
            ).scalar()
            
            if not latest_version:
                return pd.DataFrame()
                
            # 2. Query all records for this session and version
            # Ordered by row_index to preserve original order
            records = db.query(DatasetRecord).filter(
                DatasetRecord.session_id == session_id,
                DatasetRecord.version == latest_version
            ).order_by(DatasetRecord.row_index).all()
            
            # 3. Convert to DataFrame
            if not records:
                return pd.DataFrame()
                
            data_list = [record.data for record in records]
            return pd.DataFrame(data_list)
            
        finally:
            db.close()

    @staticmethod
    def get_version(session_id: uuid.UUID, version: int) -> pd.DataFrame:
        """Retrieves a specific version of the dataset as a Pandas DataFrame."""
        db: Session = SessionLocal()
        try:
            records = db.query(DatasetRecord).filter(
                DatasetRecord.session_id == session_id,
                DatasetRecord.version == version
            ).order_by(DatasetRecord.row_index).all()
            
            if not records:
                return pd.DataFrame()
                
            data_list = [record.data for record in records]
            return pd.DataFrame(data_list)
            
        finally:
            db.close()


def _json_safe_value(value: Any) -> Any:
    """Convert pandas missing scalar values and non-serializable objects (like Timestamp) to JSONB-safe values."""
    import numpy as np
    import pandas as pd
    from datetime import datetime, date

    if isinstance(value, dict):
        return {key: _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    
    # Handle pandas NA/NaN/Nat
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    # Handle datetime/date/Timestamp
    if isinstance(value, (datetime, date)) or hasattr(value, "isoformat"):
        return value.isoformat()

    # Handle numpy types
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return [_json_safe_value(item) for item in value.tolist()]

    return value
