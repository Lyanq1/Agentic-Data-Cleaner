from __future__ import annotations

from uuid import uuid4

import numpy as np
import pandas as pd
import pytest
from fastapi.encoders import jsonable_encoder

from app.services.lineage_service import LineageService
from app.services.report_service import ReportService


def test_compare_preview_converts_dataframe_values_to_json_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = pd.DataFrame(
        [
            {
                "integer": np.int64(1),
                "float": np.float64(1.25),
                "boolean": np.bool_(True),
                "timestamp": pd.Timestamp("2026-07-25T10:30:00"),
                "missing": np.nan,
                "array": np.array([np.int64(1), np.int64(2)]),
                "nested": {"count": np.int64(3)},
            }
        ]
    )
    after = pd.DataFrame(
        [
            {
                "integer": np.int64(2),
                "float": np.float64(2.5),
                "boolean": np.bool_(False),
                "timestamp": pd.Timestamp("2026-07-26T10:30:00"),
                "missing": pd.NA,
                "array": np.array([np.int64(2), np.int64(3)]),
                "nested": {"count": np.int64(4)},
            }
        ]
    )

    monkeypatch.setattr(LineageService, "get_version", lambda *_args: before)
    monkeypatch.setattr(LineageService, "get_latest_version", lambda *_args: after)

    result = ReportService.build_dataset_compare_preview(
        {"session_id": str(uuid4())},
        limit=100,
    )

    encoded = jsonable_encoder(result)
    before_row = encoded["before_rows"][0]
    after_row = encoded["after_rows"][0]

    assert before_row == {
        "integer": 1,
        "float": 1.25,
        "boolean": True,
        "timestamp": "2026-07-25T10:30:00",
        "missing": None,
        "array": [1, 2],
        "nested": {"count": 3},
    }
    assert after_row == {
        "integer": 2,
        "float": 2.5,
        "boolean": False,
        "timestamp": "2026-07-26T10:30:00",
        "missing": None,
        "array": [2, 3],
        "nested": {"count": 4},
    }
    assert encoded["changed_cell_count"] == 6
    assert all(isinstance(cell["row_index"], int) for cell in encoded["changed_cells"])
