"""Unit tests for profile_dataframe tool."""
import pandas as pd
import pytest
from pathlib import Path


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    """Create a small sample CSV file for testing."""
    df = pd.DataFrame({
        "name": ["Alice", "Bob", None, "Alice"],
        "age": [25, 30, 22, 25],
        "score": [90.5, None, 85.0, 90.5],
    })
    path = tmp_path / "sample.csv"
    df.to_csv(path, index=False)
    return path


def test_profile_basic(sample_csv: Path):
    """profile_dataframe should return shape, duplicates, and per-column stats."""
    from app.tools.data.profile_dataframe import profile_dataframe
    result = profile_dataframe.invoke({"file_path": str(sample_csv)})
    assert result["shape"] == [4, 3]
    assert result["duplicate_rows"] == 1
    assert "name" in result["columns"]
    assert result["columns"]["name"]["missing_count"] == 1
