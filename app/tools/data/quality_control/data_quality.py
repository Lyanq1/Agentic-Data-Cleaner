import pandas as pd
from typing import List, Optional

def check_nulls(df: pd.DataFrame, lazy: bool = False) -> pd.DataFrame:
    """
    Check for null values across all columns in the DataFrame using Pandas.
    
    Args:
        df (pd.DataFrame): The DataFrame to validate.
        lazy (bool): Parameter kept for compatibility, but eager evaluation is used.
                     
    Returns:
        pd.DataFrame: The validated DataFrame if no nulls are found.
        Raises ValueError if nulls are found.
    """
    null_counts = df.isnull().sum()
    columns_with_nulls = null_counts[null_counts > 0]
    
    if not columns_with_nulls.empty:
        raise ValueError(f"DataFrame contains null values in columns: {columns_with_nulls.to_dict()}")
        
    return df


def check_duplicates(df: pd.DataFrame, subset: Optional[List[str]] = None, lazy: bool = False) -> pd.DataFrame:
    """
    Check for duplicate rows in the DataFrame using Pandas.
    
    Args:
        df (pd.DataFrame): The DataFrame to validate.
        subset (List[str], optional): Only consider certain columns for identifying duplicates.
        lazy (bool): Parameter kept for compatibility, but eager evaluation is used.
                     
    Returns:
        pd.DataFrame: The validated DataFrame if no duplicates are found.
        Raises ValueError if duplicates are found.
    """
    if df.duplicated(subset=subset, keep='first').any():
        raise ValueError("DataFrame contains duplicate rows")
        
    return df
