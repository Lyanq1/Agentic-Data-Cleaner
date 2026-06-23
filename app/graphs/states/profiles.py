"""State models for semantic profiling."""

from pydantic import BaseModel, Field

class ColumnSemanticProfileDetail(BaseModel):
    description: str = Field(description="A clear business description of the column.")
    logical_group: str = Field(
        description="The logical group this column belongs to (e.g. Identity, Pricing, Address)."
    )
    relationships: list[str] = Field(
        default_factory=list,
        description=(
            "Cross-column relationships or functional dependencies "
            "(e.g., 'zip_code -> city')."
        ),
    )
    allow_missing: bool = Field(
        description="True if missing/null values are acceptable from a business standpoint."
    )
    allow_missing_reason: str = Field(default="", description="Reasoning explaining allow_missing.")
    expected_type: str = Field(
        description="Ideal semantic type: int | float | str | bool | date | datetime | time."
    )
    expected_type_reason: str = Field(default="", description="Reasoning explaining expected_type.")
    potential_dmv: list[str] = Field(
        default_factory=list, description="List of common disguised missing values detected."
    )
    potential_dmv_reason: str = Field(default="", description="Reasoning explaining potential_dmv.")
    expected_str_pattern: str | None = Field(
        default=None, description="Expected regex or string format pattern."
    )
    expected_str_pattern_reason: str | None = Field(
        default=None, description="Reasoning explaining expected_str_pattern."
    )
    semantic_data_type: str = Field(
        default="Nominal",
        description=(
            "The semantic data type of the column according to fill_strategy_summary.md "
            "(Continuous | Discrete | Nominal | Ordinal | Temporal | Free text + Geospatial | "
            "Structured text | Boolean | Identifier)."
        )
    )
    semantic_data_type_reason: str = Field(
        default="",
        description="Reasoning explaining semantic_data_type classification."
    )
    fill_strategies: list[str] = Field(
        default_factory=list,
        description="Pre-assigned null-filling strategies for this column based on its semantic data type."
    )

    # Combined Semantic Review / Quality Audit
    is_error: bool = Field(
        description=(
            "True if statistical reality deviates from business rules "
            "or has other anomalies."
        )
    )
    error_types: list[str] = Field(
        default_factory=list,
        description=(
            "Subset of 'missing' | 'type_mismatch' | 'dmv' | "
            "'string_outlier' | 'numeric_outlier'."
        ),
    )
    error_reason: str | None = Field(
        default=None, description="Detailed explanation of the error if is_error is True."
    )

class SemanticProfile(BaseModel):
    table_summary: str = Field(
        description="Concise description of the overall business purpose of the dataset."
    )
    thinking: str = Field(
        default="", description="Chain of thought thinking behind the semantic profile."
    )
    columns: dict[str, ColumnSemanticProfileDetail] = Field(
        default_factory=dict, description="Detailed semantic profile per column."
    )
