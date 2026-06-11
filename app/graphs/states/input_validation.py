"""State models for input validation and clarifications."""

from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator

class AllowMissingConfirmationQuestion(BaseModel):
    """Question that lists allow_missing=True and allow_missing=False columns for user confirmation."""

    question: str = Field(description="The confirmation question text.")
    allow_missing_columns: list[str] = Field(
        default_factory=list,
        description="Columns the semantic profiler considers nullable (allow_missing=True).",
    )
    not_allow_missing_columns: list[str] = Field(
        default_factory=list,
        description="Columns the semantic profiler considers non-nullable (allow_missing=False).",
    )
    answer: dict[str, bool] | None = Field(
        default=None,
        description=(
            "User-confirmed allow_missing value per column. "
            "Mapping of column_name → true/false after user review. "
            "None while unanswered."
        ),
    )

class StrategyQuestion(BaseModel):
    question: str = Field(description="The strategy question text.")
    options: list[str] = Field(description="Exactly 3 distinct options.")
    consequences: Any | None = Field(default=None, description="Consequences of each option.")
    answer: str | None = Field(default=None, description="The user's selected option/answer.")

class InsightQuestion(BaseModel):
    question: str = Field(description="The insight question text.")
    insight: str = Field(description="The semantic insight revealed.")
    confirm: str = Field(description="The yes/no confirmation ask.")
    answer: str | None = Field(
        default=None, description="The user's answer ('yes', 'no', or comment)."
    )
class NullClarifications(BaseModel):
    model_config = {"extra": "allow"}

    Q1_strategy: StrategyQuestion | None = None
    Q2_semantic_insight: InsightQuestion | None = None
    Q3_semantic_insight: InsightQuestion | None = None

class DuplicateClarifications(BaseModel):
    Q1_strategy: StrategyQuestion | None = None
    Q2_semantic_insight: InsightQuestion | None = None
    Q3_semantic_insight: InsightQuestion | None = None

class TypecastClarifications(BaseModel):
    Q1_semantic_insight: InsightQuestion | None = None
    Q2_semantic_insight: InsightQuestion | None = None
    Q3_semantic_insight: InsightQuestion | None = None

class ClarificationIssues(BaseModel):
    null: NullClarifications | None = None
    duplicate: DuplicateClarifications | None = None
    typecast: TypecastClarifications | None = None

class ActionPlan(BaseModel):
    null: str | None = None
    duplicate: str | None = None
    typecast: str | None = None

    @field_validator("null", "duplicate", "typecast", mode="before")
    @classmethod
    def convert_to_string(cls, v: Any) -> str | None:  # noqa: ANN401
        if v is None:
            return None
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            return " | ".join(f"{k}: {val}" for k, val in v.items())
        if isinstance(v, list):
            return ", ".join(str(item) for item in v)
        return str(v)

class InputValidationResult(BaseModel):
    """Structured output expected from the Input Validator LLM."""

    status: Literal["ready", "needs_clarification"] = Field(
        description="The status of the validation. 'ready' or 'needs_clarification'."
    )
    reasoning: str = Field(description="Brief reasoning explaining the status.")
    resolved_by_user: list[str] = Field(
        default_factory=list,
        description="List of issues and columns resolved by the user's request.",
    )
    action_plan: ActionPlan | None = Field(
        default=None, description="The plan for each issue if status is 'ready'."
    )
    clarifications: ClarificationIssues | None = Field(
        default=None,
        description="Clarifications needed per active issue if status is 'needs_clarification'.",
    )
