"""Models used by the ReAct Validator Agent."""

from typing import Any, List, Dict
from pydantic import BaseModel, Field


class ValidatorOutput(BaseModel):
    """Structured output expected from the Validator LLM."""

    passed: bool = Field(
        description="True if the dataset passes validation, False if it needs rework."
    )
    quality_score: int = Field(
        description="A score from 0 to 100 representing the quality of the dataset."
    )
    score_breakdown: Dict[str, int] = Field(
        description="A breakdown of how the score was calculated (e.g. {'nulls': -20, 'duplicates': -10}).",
        default_factory=dict
    )
    failed_rules: List[str] = Field(
        description="A list of rule names that failed, if any.",
        default_factory=list
    )
    replan_hints: Dict[str, Any] = Field(
        description="Hints or suggestions to pass to the planner/worker on how to fix the issues.",
        default_factory=dict
    )
    reasoning: str = Field(
        description="Brief reasoning explaining the validation decision."
    )
