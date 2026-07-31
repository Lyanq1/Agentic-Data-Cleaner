from __future__ import annotations

import json

import pandas as pd
import pytest

from app.graphs.states.output_validation import TaskVerification
from app.graphs.states.planning import TaskDetail
from app.graphs.states.profiles import ColumnSemanticProfileDetail, SemanticProfile
from app.tools.data.quality_control.tool import perform_data_quality_check_df
from app.tools.data.quality_control.validator import (
    PandasValidationErrors,
    get_approved_dmv_sentinels,
    validate_dataframe,
)

DMV_OVERRIDE = {
    "allow_fill_value_as_sentinel": True,
    "acknowledged_value": "N/A",
    "acknowledged_by_user": True,
}
PATTERN_OVERRIDE = {
    "allow_fill_value_mismatch": True,
    "acknowledged_value": "N/A",
    "acknowledged_by_user": True,
}


def _task(
    validation_overrides: dict | None = None,
    fill_value: str = "N/A",
) -> TaskDetail:
    return TaskDetail(
        task_id="null_handling",
        agent="null_agent",
        skip=False,
        columns=["Sample"],
        verification=TaskVerification(),
        strategy={
            "per_column": {
                "Sample": {
                    "strategy": "fill_value",
                    "fill_value": fill_value,
                    "validation_overrides": validation_overrides or {},
                }
            }
        },
    )


def _failed_rules(
    dataframe: pd.DataFrame,
    task: TaskDetail,
    semantic_profile: SemanticProfile,
) -> set[str]:
    with pytest.raises(PandasValidationErrors) as exc_info:
        validate_dataframe(dataframe, task, semantic_profile)
    return {error.check for error in exc_info.value.errors}


def test_fill_value_requires_both_dmv_and_pattern_approvals() -> None:
    dataframe = pd.DataFrame({"Sample": ["33 patients", "N/A"]})
    semantic_profile = SemanticProfile(
        table_summary="Hospital measures",
        columns={
            "Sample": ColumnSemanticProfileDetail(
                description="Number of patients in the measure sample",
                logical_group="Measure",
                allow_missing=False,
                expected_type="str",
                potential_dmv=["N/A"],
                expected_str_pattern=r"^\d+ patients$",
                semantic_data_type="Structured text",
                fill_strategies=["fill_value"],
                is_error=True,
            )
        },
    )

    assert _failed_rules(dataframe, _task(), semantic_profile) == {
        "no_disguised_missing_values",
        "expected_str_pattern",
    }
    assert _failed_rules(
        dataframe,
        _task({"potential_dmv": DMV_OVERRIDE}),
        semantic_profile,
    ) == {"expected_str_pattern"}
    assert _failed_rules(
        dataframe,
        _task({"expected_str_pattern": PATTERN_OVERRIDE}),
        semantic_profile,
    ) == {"no_disguised_missing_values"}

    approved_task = _task(
        {
            "potential_dmv": DMV_OVERRIDE,
            "expected_str_pattern": PATTERN_OVERRIDE,
        }
    )
    validate_dataframe(dataframe, approved_task, semantic_profile)

    approved_sentinels = {
        column: [str(value)]
        for column, value in get_approved_dmv_sentinels(approved_task).items()
    }
    quality_report = json.loads(
        perform_data_quality_check_df(
            dataframe,
            allowed_disguised_values=approved_sentinels,
        )
    )
    assert quality_report["passed"] is True
    assert quality_report["columns_with_disguised_nulls"] == []

    changed_value_task = _task(
        {
            "potential_dmv": DMV_OVERRIDE,
            "expected_str_pattern": PATTERN_OVERRIDE,
        },
        fill_value="Unknown",
    )
    assert get_approved_dmv_sentinels(changed_value_task) == {}

    remaining_dmv_report = json.loads(
        perform_data_quality_check_df(
            pd.DataFrame({"Sample": ["33 patients", "N/A", "unknown"]}),
            allowed_disguised_values=approved_sentinels,
        )
    )
    assert remaining_dmv_report["passed"] is False
    assert remaining_dmv_report["columns"][0]["disguised_nulls"] == {"unknown": 1}
