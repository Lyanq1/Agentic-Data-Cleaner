"""Small helpers for resolving lineage identifiers from graph state."""

from pathlib import Path
from typing import Any, Mapping
from uuid import UUID


def resolve_lineage_session_id(state: Mapping[str, Any]) -> UUID | None:
    """Resolve the lineage session UUID from graph state.

    Preferred source is ``session_id``. ``project_id`` and ``dataset_path`` are kept as
    compatibility fallbacks while the pipeline state contract settles.
    """
    for key in ("session_id", "project_id"):
        session_id = parse_uuid(state.get(key))
        if session_id:
            return session_id

    dataset_path = state.get("dataset_path")
    if isinstance(dataset_path, str) and dataset_path:
        return parse_uuid(Path(dataset_path).stem)

    return None


def parse_uuid(value: Any) -> UUID | None:
    """Parse UUID values without raising for invalid state fields."""
    if isinstance(value, UUID):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None
