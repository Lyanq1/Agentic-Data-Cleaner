"""Models used by the deterministic Pandera validator."""

from dataclasses import dataclass, field
from typing import Any

from app.graphs.states.global_state import TaskDetail


@dataclass(slots=True)
class ValidationOutcome:
    """Normalized result returned by the Pandera validation runner."""

    task: TaskDetail | None
    passed: bool
    skipped: bool = False
    failed_rules: list[str] = field(default_factory=list)
    message: dict[str, Any] | str | None = None
    failure_cases: list[dict[str, Any]] = field(default_factory=list)

    @property
    def task_id(self) -> str:
        """Return a stable task id for logging."""
        return self.task.task_id if self.task else "unknown"

    @property
    def agent(self) -> str:
        """Return a stable agent name for logging."""
        if self.task is None:
            return "unknown"
        return getattr(self.task.agent, "value", str(self.task.agent))

    def compact_error_log(self) -> str:
        """Return a concise error payload suitable for worker retry logs."""
        if self.passed:
            return ""
        return str(
            {
                "task_id": self.task_id,
                "failed_rules": self.failed_rules,
                "message": self.message,
                "failure_cases": self.failure_cases[:20],
            }
        )
