"""Build final pipeline reports, exports, diagrams, and grounded report answers."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import text

from app.core.database import engine, SessionLocal
from app.core.llm_factory import create_llm
from app.graphs.utils import _load_dataframe
from app.models.lineage import ReportChatMessage
from app.services.dataframe_order import restore_original_column_order
from app.services.lineage_service import LineageService
from app.services.lineage_utils import resolve_lineage_session_id


_DIAGRAM_STYLE_LINES = [
    "    classDef source fill:#DBEAFE,stroke:#2563EB,color:#1E3A8A,stroke-width:2px",
    "    classDef profile fill:#E0E7FF,stroke:#4F46E5,color:#312E81,stroke-width:2px",
    "    classDef plan fill:#F3E8FF,stroke:#9333EA,color:#581C87,stroke-width:2px",
    "    classDef dedup fill:#FEF3C7,stroke:#D97706,color:#78350F,stroke-width:2px",
    "    classDef nulls fill:#CFFAFE,stroke:#0891B2,color:#164E63,stroke-width:2px",
    "    classDef typecast fill:#FCE7F3,stroke:#DB2777,color:#831843,stroke-width:2px",
    "    classDef validation fill:#CCFBF1,stroke:#0D9488,color:#134E4A,stroke-width:2px",
    "    classDef process fill:#EDE9FE,stroke:#7C3AED,color:#4C1D95,stroke-width:2px",
    "    classDef final fill:#DCFCE7,stroke:#16A34A,color:#14532D,stroke-width:3px",
    "    linkStyle default stroke:#64748B,stroke-width:2px",
]


def _diagram_class_for_agent(agent_name: Any) -> str:
    """Map lineage agents to a stable, readable Mermaid color class."""
    normalized = str(agent_name or "").lower()
    if "ingest" in normalized or "upload" in normalized:
        return "source"
    if "dedup" in normalized:
        return "dedup"
    if "null" in normalized:
        return "nulls"
    if "type" in normalized or "cast" in normalized:
        return "typecast"
    if "valid" in normalized:
        return "validation"
    if "profil" in normalized:
        return "profile"
    if "plan" in normalized:
        return "plan"
    if "report" in normalized:
        return "final"
    return "process"


def _model_to_dict(value: Any) -> Any:
    """Convert Pydantic/state objects to JSON-compatible nested data."""
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, dict):
        return {str(key): _model_to_dict(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_model_to_dict(item) for item in value]
    return value


def _safe_len(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _profile_columns(profile: dict[str, Any] | None) -> dict[str, Any]:
    if not profile:
        return {}
    columns = profile.get("columns") or {}
    if isinstance(columns, list):
        return {
            str(item.get("column_name")): item
            for item in columns
            if isinstance(item, dict) and item.get("column_name")
        }
    if isinstance(columns, dict):
        return columns
    return {}


def _count_missing_values(profile: dict[str, Any] | None) -> int:
    total = 0
    for column in _profile_columns(profile).values():
        if not isinstance(column, dict):
            continue
        total += int(
            column.get("null_count")
            or column.get("missing_count")
            or (column.get("categorical_stats") or {}).get("missing_count")
            or (column.get("numeric_stats") or {}).get("missing_count")
            or 0
        )
    return total


def _load_latest_processed_dataframe(state: dict[str, Any]):
    session_id = resolve_lineage_session_id(state)
    if session_id:
        try:
            dataframe = LineageService.get_latest_version(session_id)
            if not dataframe.empty:
                return restore_original_column_order(dataframe, state)
        except Exception:
            pass

    for key in ("physical_dataframe_path", "dataset_path"):
        path = state.get(key)
        if not path:
            continue
        try:
            return _load_dataframe(path)
        except Exception:
            continue
    return None


def _execution_plan_summary(plan_value: Any) -> dict[str, Any]:
    plan = _model_to_dict(plan_value) or {}
    tasks: list[dict[str, Any]] = []
    for wrapper in plan.get("task_list") or []:
        work_order = wrapper.get("work_order") if isinstance(wrapper, dict) else None
        if not isinstance(work_order, dict):
            continue
        tasks.append(
            {
                "task_id": work_order.get("task_id"),
                "agent": work_order.get("agent"),
                "columns": work_order.get("columns") or [],
                "skip": bool(work_order.get("skip")),
                "skip_reason": work_order.get("skip_reason"),
                "rationale": work_order.get("rationale"),
            }
        )
    return {
        "plan_summary": plan.get("plan_summary", ""),
        "tasks": tasks,
        "active_task_count": len([task for task in tasks if not task["skip"]]),
        "skipped_task_count": len([task for task in tasks if task["skip"]]),
    }


def _validation_summary(validation_results: list[Any]) -> dict[str, Any]:
    items = [_model_to_dict(item) for item in validation_results or []]
    issues: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        for rule in item.get("failed_rules") or []:
            issues.append(
                {
                    "severity": "error",
                    "column": item.get("task_id") or item.get("agent") or "validation",
                    "issue_type": "Validation Failure",
                    "description": f"Rule '{rule}' failed validation on agent '{item.get('agent', 'unknown')}'.",
                    "affected_rows": (item.get("metrics_observed") or {}).get("failed_count", 0),
                }
            )
    return {
        "passed": all(bool(item.get("passed", True)) for item in items if isinstance(item, dict)),
        "items": items,
        "issues": issues,
        "issue_count": len(issues),
    }


def _worker_result_lines(worker_outputs: dict[str, Any] | None) -> list[str]:
    if not worker_outputs:
        return []
    lines: list[str] = []
    for agent_name, raw_result in worker_outputs.items():
        result = _model_to_dict(raw_result)
        if isinstance(result, dict):
            task_id = result.get("task_id") or result.get("agent_name") or agent_name
            status = result.get("status") or result.get("outcome") or "completed"
            changed_rows = result.get("changed_rows") or result.get("rows_removed") or result.get("rows_affected")
            suffix = f"; affected rows: {changed_rows}" if changed_rows is not None else ""
            lines.append(f"{task_id}: {status}{suffix}")
        else:
            lines.append(f"{agent_name}: completed")
    return lines


def _next_actions(report: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    validation = report.get("validation") or {}
    if validation.get("issue_count", 0) > 0:
        actions.append("Review remaining validation issues before using the cleaned dataset downstream.")
    if report.get("profile_summary", {}).get("missing_values_detected", 0) > 0:
        actions.append("Inspect columns with missing values and consider adding stricter null-handling rules.")
    if report.get("lineage", {}).get("version_count", 0) > 1:
        actions.append("Use the lineage diagram to explain which agent produced each approved dataset version.")
    actions.append("Download the cleaned dataset and use the report as documentation for downstream analysis.")
    actions.append("Ask the Report Agent about specific columns before planning the next transformation.")
    return actions


def _suggested_questions(report: dict[str, Any]) -> list[str]:
    """Create grounded starter questions from the actual report contents."""
    questions: list[str] = []
    lineage = report.get("lineage") or {}
    validation = report.get("validation") or {}
    metrics = report.get("metrics") or {}

    if report.get("transformations"):
        questions.append("What changed after cleaning, and which steps made those changes?")
    if lineage.get("version_count", 0) > 0:
        questions.append("Which agent produced each approved dataset version?")
    if validation.get("issue_count", 0) > 0:
        questions.append("Which validation issues remain and what should I review first?")
    else:
        questions.append("Did final validation pass, and what evidence supports that?")
    if metrics.get("f1_metrics"):
        questions.append("How should I interpret the F1-score evaluation for this run?")
    if report.get("next_actions"):
        questions.append("What should I transform or validate next?")

    # Keep the UI focused and avoid suggestions unsupported by the current report.
    return questions[:4]


def _compact_for_prompt(value: Any, *, max_chars: int = 16000) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... <context truncated>"


def _extract_json_object(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _normalize_cell(value: Any) -> str:
    try:
        if pd.isna(value):
            return "__null__"
    except (TypeError, ValueError):
        pass
    text_value = str(value).strip()
    if text_value.lower() in {"", "nan", "none", "null", "nat"}:
        return "__null__"
    return text_value


def _display_cell(value: Any) -> Any:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _contains_column_reference(value: Any, column_name: str) -> bool:
    """Return True when a nested artifact appears to reference a column."""
    target = column_name.lower()
    if isinstance(value, str):
        return value.lower() == target or target in value.lower()
    if isinstance(value, dict):
        return any(
            _contains_column_reference(key, column_name)
            or _contains_column_reference(item, column_name)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_column_reference(item, column_name) for item in value)
    return False


class ReportService:
    """Builds the final Report Agent artifacts from pipeline state and lineage."""

    @staticmethod
    def build_report(run_id: str, state: dict[str, Any]) -> dict[str, Any]:
        profile = _model_to_dict(state.get("data_profile") or state.get("statistical_profile")) or {}
        semantic_profile = _model_to_dict(state.get("semantic_profile")) or {}
        worker_outputs = _model_to_dict(state.get("worker_outputs")) or {}
        validation = _validation_summary(state.get("validation_results") or [])
        plan_summary = _execution_plan_summary(state.get("execution_plan"))
        lineage_versions: list[dict[str, Any]] = []

        session_id = resolve_lineage_session_id(state)
        if session_id:
            try:
                lineage_versions = LineageService.list_versions(session_id)
            except Exception:
                lineage_versions = []

        processed_df = _load_latest_processed_dataframe(state)
        output_rows = int(len(processed_df)) if processed_df is not None else None
        output_columns = [str(col) for col in processed_df.columns] if processed_df is not None else []
        profile_columns = _profile_columns(profile)
        input_rows = profile.get("total_rows") or profile.get("row_count") or output_rows or 0
        tracked_columns = output_columns or list(profile_columns.keys())

        transformations = [
            "Canonical dataset conversion and normalization completed.",
            "Statistical and semantic profiling completed.",
        ]
        transformations.extend(_worker_result_lines(worker_outputs))
        if validation["passed"]:
            transformations.append("Final validation passed for the approved cleaning outputs.")

        token_metrics = state.get("token_metrics") or {}
        validation_metrics = {
            "Intent Analysis": {
                "Matched Columns": len(tracked_columns),
                "Tracked Columns": len(tracked_columns),
                "Missing values detected": _count_missing_values(profile),
            }
        }
        if state.get("f1_metrics"):
            validation_metrics["F1-Score Evaluation"] = state.get("f1_metrics")
        validation["metrics"] = validation_metrics

        report = {
            "run_id": run_id,
            "filename": state.get("original_filename") or "dataset.parquet",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "input_rows": int(input_rows or 0),
                "output_rows": output_rows,
                "tracked_columns": len(tracked_columns),
                "column_names": tracked_columns,
                "completed_steps": state.get("completed_steps") or [],
                "retry_cycles": int(state.get("retry_count") or 0),
                "total_tokens_used": int(token_metrics.get("total_tokens", 0)),
            },
            "profile_summary": {
                "total_rows": int(input_rows or 0),
                "total_columns": len(profile_columns) or len(tracked_columns),
                "missing_values_detected": _count_missing_values(profile),
                "duplicate_rows": profile.get("duplicate_rows", 0),
            },
            "semantic_summary": {
                "table_summary": semantic_profile.get("table_summary", ""),
                "column_count": len(semantic_profile.get("columns") or {}),
            },
            "execution_plan_summary": plan_summary,
            "worker_results": worker_outputs,
            "validation": validation,
            "lineage": {
                "session_id": str(session_id) if session_id else None,
                "versions": lineage_versions,
                "version_count": len(lineage_versions),
                "latest_version": lineage_versions[-1]["version"] if lineage_versions else None,
            },
            "metrics": {
                "token_metrics": token_metrics,
                "f1_metrics": state.get("f1_metrics"),
            },
            "transformations": transformations,
            "next_actions": [],
            "suggested_questions": [],
            "pipeline_context": {
                "user_prompt": state.get("user_prompt") or "",
                "input_validation_result": _model_to_dict(state.get("input_validation_result")),
                "completed_steps": state.get("completed_steps") or [],
                "current_step": state.get("current_step"),
                "task_list": state.get("task_list") or [],
                "current_task_idx": state.get("current_task_idx"),
                "agent_logs": _model_to_dict(state.get("agent_logs")) or {},
            },
        }
        report["next_actions"] = _next_actions(report)
        report["suggested_questions"] = _suggested_questions(report)
        return report

    @staticmethod
    def build_column_change_summary(
        state: dict[str, Any],
        columns: list[str] | None = None,
        sample_limit: int = 8,
        max_columns: int = 12,
    ) -> dict[str, Any]:
        """Compare initial lineage version against the latest approved version."""
        session_id = resolve_lineage_session_id(state)
        if not session_id:
            return {
                "available": False,
                "reason": "No lineage session id is available for this run.",
                "columns": {},
            }

        try:
            before_df = LineageService.get_version(session_id, 1)
            after_df = LineageService.get_latest_version(session_id)
        except Exception as exc:
            return {
                "available": False,
                "reason": f"Failed to load lineage versions: {exc}",
                "columns": {},
            }

        if before_df.empty or after_df.empty:
            return {
                "available": False,
                "reason": "Before or after dataframe is empty.",
                "columns": {},
            }

        before_df = restore_original_column_order(before_df, state)
        after_df = restore_original_column_order(after_df, state)
        available_columns = [str(col) for col in after_df.columns if col in before_df.columns]
        selected_columns = columns or available_columns
        selected_columns = [
            column for column in selected_columns
            if column in available_columns
        ]

        max_rows = min(len(before_df), len(after_df))
        result: dict[str, Any] = {
            "available": True,
            "session_id": str(session_id),
            "before_version": 1,
            "after_version": "latest",
            "before_rows": int(len(before_df)),
            "after_rows": int(len(after_df)),
            "row_count_delta": int(len(after_df) - len(before_df)),
            "columns": {},
        }

        for column in selected_columns:
            before_series = before_df.iloc[:max_rows][column]
            after_series = after_df.iloc[:max_rows][column]
            before_norm = before_series.map(_normalize_cell)
            after_norm = after_series.map(_normalize_cell)
            changed_mask = before_norm != after_norm
            changed_indices = list(changed_mask[changed_mask].index[:sample_limit])
            samples = [
                {
                    "row_index": int(index),
                    "before": _display_cell(before_df.at[index, column]),
                    "after": _display_cell(after_df.at[index, column]),
                }
                for index in changed_indices
            ]
            result["columns"][column] = {
                "changed_cells": int(changed_mask.sum()),
                "compared_rows": int(max_rows),
                "change_rate": round(float(changed_mask.sum() / max_rows), 4) if max_rows else 0.0,
                "before_nulls": int(before_series.isna().sum()),
                "after_nulls": int(after_series.isna().sum()),
                "null_delta": int(after_series.isna().sum() - before_series.isna().sum()),
                "before_dtype": str(before_series.dtype),
                "after_dtype": str(after_series.dtype),
                "samples": samples,
            }
        if columns is None and len(result["columns"]) > max_columns:
            top_items = sorted(
                result["columns"].items(),
                key=lambda item: item[1].get("changed_cells", 0),
                reverse=True,
            )[:max_columns]
            result["columns"] = dict(top_items)
            result["truncated_to_top_changed_columns"] = True
        return result

    @staticmethod
    def build_top_changed_columns(
        state: dict[str, Any],
        limit: int = 10,
        sample_limit: int = 3,
    ) -> dict[str, Any]:
        """Return the columns with the largest before/after cell changes."""
        evidence = ReportService.build_column_change_summary(
            state,
            columns=None,
            sample_limit=sample_limit,
            max_columns=max(1, limit),
        )
        if not evidence.get("available"):
            return evidence
        ranked = sorted(
            evidence.get("columns", {}).items(),
            key=lambda item: item[1].get("changed_cells", 0),
            reverse=True,
        )[: max(1, limit)]
        evidence["columns"] = dict(ranked)
        evidence["ranking_basis"] = "changed_cells_between_lineage_v1_and_latest"
        return evidence

    @staticmethod
    def build_column_impact_summary(
        report: dict[str, Any],
        state: dict[str, Any],
        column_name: str,
    ) -> dict[str, Any]:
        """Explain how a column participates in the current pipeline artifacts."""
        known_columns = [str(column) for column in (report.get("summary") or {}).get("column_names") or []]
        matched_column = next(
            (column for column in known_columns if column.lower() == column_name.lower()),
            column_name,
        )
        plan_tasks = []
        for task in (report.get("execution_plan_summary") or {}).get("tasks", []):
            if _contains_column_reference(task.get("columns") or [], matched_column) or _contains_column_reference(task, matched_column):
                plan_tasks.append(task)

        worker_outputs = report.get("worker_results") or {}
        worker_matches = []
        if isinstance(worker_outputs, dict):
            for agent_name, output in worker_outputs.items():
                if _contains_column_reference(output, matched_column):
                    worker_matches.append({"agent": agent_name, "output": output})

        validation_matches = []
        for item in (report.get("validation") or {}).get("items") or []:
            if _contains_column_reference(item, matched_column):
                validation_matches.append(item)

        semantic_profile = _model_to_dict(state.get("semantic_profile")) or {}
        semantic_columns = semantic_profile.get("columns") or {}
        semantic_context = None
        if isinstance(semantic_columns, dict):
            semantic_context = semantic_columns.get(matched_column)

        change_evidence = ReportService.build_column_change_summary(
            state,
            columns=[matched_column],
            sample_limit=8,
        )

        downstream_scope = [
            "final report summary",
            "validation findings",
            "lineage diagram",
            "exported cleaned dataset",
            "Report Agent Q&A",
        ]
        if plan_tasks:
            downstream_scope.append("execution plan explanation")
        if worker_matches:
            downstream_scope.append("worker result explanation")

        return {
            "column": matched_column,
            "known_column": matched_column in known_columns,
            "semantic_context": semantic_context,
            "plan_tasks": plan_tasks,
            "worker_matches": worker_matches,
            "validation_matches": validation_matches,
            "change_evidence": change_evidence,
            "downstream_scope": downstream_scope,
            "scope_note": (
                "Impact is evaluated inside the current data-cleaning run. "
                "This is not a dbt project-wide downstream model graph."
            ),
        }

    @staticmethod
    def infer_requested_columns(report: dict[str, Any], question: str) -> list[str]:
        """Find columns mentioned in a free-form question."""
        known_columns: set[str] = set()
        for column in (report.get("summary") or {}).get("column_names") or []:
            known_columns.add(str(column))
        for task in (report.get("execution_plan_summary") or {}).get("tasks", []):
            for column in task.get("columns") or []:
                known_columns.add(str(column))
        worker_outputs = report.get("worker_results") or {}
        if isinstance(worker_outputs, dict):
            for value in worker_outputs.values():
                if isinstance(value, dict):
                    for column in value.get("columns") or value.get("changed_columns") or []:
                        known_columns.add(str(column))
        metrics = (report.get("validation") or {}).get("metrics") or {}
        known_columns.update(str(column) for column in metrics.keys())

        question_lower = question.lower()
        requested = [
            column for column in known_columns
            if re.search(rf"(?<!\w){re.escape(column.lower())}(?!\w)", question_lower)
        ]
        return requested

    @staticmethod
    def build_pipeline_diagram(report: dict[str, Any]) -> str:
        task_nodes = [
            task["task_id"]
            for task in (report.get("execution_plan_summary") or {}).get("tasks", [])
            if task.get("task_id") and not task.get("skip")
        ]
        if not task_nodes:
            task_nodes = ["cleaning_tasks"]

        lines = [
            "flowchart LR",
            "    upload[Upload Dataset] --> profiler[Statistical Profiler]",
            "    profiler --> semantic[Semantic Profiler]",
            "    semantic --> input_validator[Input Validator]",
            "    input_validator --> planner[Planner]",
        ]
        previous = "planner"
        task_node_ids = []
        validator_node_ids = []
        for index, task in enumerate(task_nodes, start=1):
            node_id = f"task{index}"
            validator_id = f"validator{index}"
            task_node_ids.append(node_id)
            validator_node_ids.append(validator_id)
            lines.append(f"    {previous} --> {node_id}[{task}]")
            lines.append(f"    {node_id} --> {validator_id}[Validator]")
            previous = validator_id
        lines.append(f"    {previous} --> report[Final Report Agent]")
        lines.extend(_DIAGRAM_STYLE_LINES)
        lines.extend([
            "    class upload source",
            "    class profiler,semantic profile",
            "    class input_validator,planner plan",
            f"    class {','.join(task_node_ids)} process",
            f"    class {','.join(validator_node_ids)} validation",
            "    class report final",
        ])
        return "\n".join(lines)

    @staticmethod
    def build_lineage_diagram(report: dict[str, Any]) -> str:
        versions = (report.get("lineage") or {}).get("versions") or []
        lines = ["flowchart LR"]
        if not versions:
            lines.append("    raw[Uploaded Dataset] --> final[Final Dataset]")
            lines.extend(_DIAGRAM_STYLE_LINES)
            lines.extend([
                "    class raw source",
                "    class final final",
            ])
            return "\n".join(lines)

        previous_id = None
        node_classes = []
        for index, version in enumerate(versions, start=1):
            node_id = f"v{index}"
            agent_name = version.get("agent_name", "agent")
            label = f"v{version.get('version')} {agent_name}"
            lines.append(f"    {node_id}[{label}]")
            node_classes.append(f"    class {node_id} {_diagram_class_for_agent(agent_name)}")
            if previous_id:
                lines.append(f"    {previous_id} --> {node_id}")
            previous_id = node_id
        lines.append(f"    {previous_id} --> final[Final Report]")
        lines.extend(_DIAGRAM_STYLE_LINES)
        lines.extend(node_classes)
        lines.append("    class final final")
        return "\n".join(lines)

    @staticmethod
    def render_markdown(report: dict[str, Any]) -> str:
        summary = report.get("summary") or {}
        validation = report.get("validation") or {}
        lineage = report.get("lineage") or {}
        lines = [
            f"# Final Cleaning Report: {report.get('filename', 'dataset')}",
            "",
            "## Summary",
            f"- Run ID: `{report.get('run_id')}`",
            f"- Input rows: {summary.get('input_rows')}",
            f"- Output rows: {summary.get('output_rows')}",
            f"- Tracked columns: {summary.get('tracked_columns')}",
            f"- Tokens used: {summary.get('total_tokens_used')}",
            "",
            "## Transformations",
        ]
        lines.extend(f"- {item}" for item in report.get("transformations") or [])
        lines.extend(
            [
                "",
                "## Validation",
                f"- Passed: {validation.get('passed')}",
                f"- Issue count: {validation.get('issue_count')}",
                "",
                "## Lineage",
                f"- Session ID: `{lineage.get('session_id')}`",
                f"- Version count: {lineage.get('version_count')}",
            ]
        )
        for version in lineage.get("versions") or []:
            lines.append(
                f"- v{version.get('version')}: {version.get('agent_name')} - {version.get('description')}"
            )
        lines.extend(["", "## Next Actions"])
        lines.extend(f"- {item}" for item in report.get("next_actions") or [])
        return "\n".join(lines) + "\n"

    @staticmethod
    def render_html(report: dict[str, Any]) -> str:
        md = ReportService.render_markdown(report)
        body = "<br>".join(html.escape(line) for line in md.splitlines())
        return f"<!doctype html><html><head><meta charset=\"utf-8\"><title>Final Cleaning Report</title></head><body><pre>{body}</pre></body></html>"

    @staticmethod
    def answer_question(report: dict[str, Any], question: str) -> dict[str, Any]:
        normalized = question.lower()
        sources = ["report"]
        f1_metrics = (report.get("metrics") or {}).get("f1_metrics") or {}
        token_metrics = (report.get("metrics") or {}).get("token_metrics") or {}
        asks_token = any(token in normalized for token in ["token", "cost", "chi phí", "ton bao nhieu", "tốn bao nhiêu", "tốn bn"])
        asks_tp = any(token in normalized for token in ["true positive", "tp", "đúng dương", "duong tinh dung"])
        asks_fp = any(token in normalized for token in ["false positive", "fp", "dương giả", "duong gia"])
        asks_fn = any(token in normalized for token in ["false negative", "fn", "âm giả", "am gia"])
        asks_precision = "precision" in normalized or "độ chính xác sửa lỗi" in normalized
        asks_recall = "recall" in normalized or "độ phủ" in normalized
        asks_accuracy = "accuracy" in normalized or "cell accuracy" in normalized or "độ chính xác" in normalized
        asks_f1 = "f1" in normalized or "f1-score" in normalized or "điểm f1" in normalized

        if asks_token:
            sources.append("token_metrics")
            answer = (
                f"This run used {token_metrics.get('total_tokens', 0)} total LLM tokens "
                f"({token_metrics.get('prompt_tokens', 0)} prompt tokens and "
                f"{token_metrics.get('completion_tokens', 0)} completion tokens)."
            )
        elif asks_tp or asks_fp or asks_fn:
            sources.append("metrics")
            if f1_metrics:
                details = []
                if asks_tp:
                    details.append(f"true positives: {f1_metrics.get('tp')}")
                if asks_fp:
                    details.append(f"false positives: {f1_metrics.get('fp')}")
                if asks_fn:
                    details.append(f"false negatives: {f1_metrics.get('fn')}")
                answer = "The F1 evaluation counts are " + ", ".join(details) + "."
            else:
                answer = "This run does not include TP/FP/FN counts because no F1-score evaluation is available."
        elif asks_precision or asks_recall or asks_accuracy or asks_f1 or "score" in normalized:
            metrics = f1_metrics
            sources.append("metrics")
            if metrics:
                requested_parts = []
                if asks_f1 or "score" in normalized:
                    requested_parts.append(f"F1 score: {metrics.get('f1_score')}")
                if asks_precision:
                    requested_parts.append(f"precision: {metrics.get('error_correction_precision')}")
                if asks_recall:
                    requested_parts.append(f"recall: {metrics.get('error_correction_recall')}")
                if asks_accuracy:
                    requested_parts.append(f"cell accuracy: {metrics.get('cell_accuracy')}")
                if not requested_parts:
                    requested_parts = [
                        f"F1 score: {metrics.get('f1_score')}",
                        f"precision: {metrics.get('error_correction_precision')}",
                        f"recall: {metrics.get('error_correction_recall')}",
                        f"cell accuracy: {metrics.get('cell_accuracy')}",
                    ]
                answer = (
                    "The F1 evaluation reports "
                    + ", ".join(requested_parts)
                    + f" across {metrics.get('total_cells_evaluated')} evaluated cells."
                )
            else:
                answer = "This run does not include an F1-score evaluation because no usable ground-truth clean file was available at report time."
        elif "lineage" in normalized or "version" in normalized or "agent" in normalized:
            lineage = report.get("lineage") or {}
            versions = lineage.get("versions") or []
            sources.append("lineage")
            if versions:
                version_lines = [
                    f"v{item.get('version')} was produced by {item.get('agent_name')}: {item.get('description') or 'no description'}"
                    for item in versions
                ]
                answer = "The approved dataset lineage is: " + "; ".join(version_lines) + "."
            else:
                answer = "No persisted lineage versions were found for this run."
        elif "valid" in normalized or "issue" in normalized or "pass" in normalized:
            validation = report.get("validation") or {}
            sources.append("validation_results")
            answer = (
                f"Validation passed: {validation.get('passed')}. "
                f"Remaining issue count: {validation.get('issue_count', 0)}."
            )
        elif "transform" in normalized or "change" in normalized or "clean" in normalized:
            sources.append("worker_outputs")
            transformations = report.get("transformations") or []
            answer = "Applied transformations: " + "; ".join(transformations)
        elif "next" in normalized or "suggest" in normalized:
            answer = "Suggested next actions: " + "; ".join(report.get("next_actions") or [])
        else:
            summary = report.get("summary") or {}
            answer = (
                f"The pipeline completed for {report.get('filename')}. "
                f"It processed {summary.get('input_rows')} input rows, produced "
                f"{summary.get('output_rows')} output rows, and tracks "
                f"{summary.get('tracked_columns')} columns."
            )

        return {
            "answer": answer,
            "sources": sources,
            "reasoning_summary": "Answered from the structured final report with deterministic fallback logic.",
            "suggested_questions": _suggested_questions(report),
        }

    @staticmethod
    def answer_column_changes_from_evidence(
        evidence: dict[str, Any] | None,
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        if not evidence or not evidence.get("available") or not evidence.get("columns"):
            return fallback
        parts: list[str] = []
        for column, summary in evidence["columns"].items():
            sample_text = ""
            samples = summary.get("samples") or []
            if samples:
                sample_text = " Examples: " + "; ".join(
                    f"row {item.get('row_index')}: {item.get('before')} -> {item.get('after')}"
                    for item in samples[:3]
                )
            parts.append(
                f"Column '{column}' changed in {summary.get('changed_cells')} of "
                f"{summary.get('compared_rows')} compared rows "
                f"({summary.get('change_rate')}). Nulls went from "
                f"{summary.get('before_nulls')} to {summary.get('after_nulls')}; dtype went "
                f"from {summary.get('before_dtype')} to {summary.get('after_dtype')}.{sample_text}"
            )
        return {
            **fallback,
            "answer": " ".join(parts),
            "sources": sorted(set([*fallback.get("sources", []), "column_change_evidence", "lineage_versions"])),
            "reasoning_summary": "Compared lineage version 1 against the latest approved version for the requested column evidence.",
        }

    @staticmethod
    def answer_top_changes_from_evidence(
        evidence: dict[str, Any] | None,
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        if not evidence or not evidence.get("available") or not evidence.get("columns"):
            return fallback
        parts = [
            f"{column}: {summary.get('changed_cells')} changed cells ({summary.get('change_rate')})"
            for column, summary in evidence["columns"].items()
            if summary.get("changed_cells", 0) > 0
        ]
        answer = (
            "The most changed columns are: " + "; ".join(parts) + "."
            if parts
            else "No cell-level changes were detected between lineage version 1 and the latest approved version."
        )
        return {
            **fallback,
            "answer": answer,
            "sources": sorted(set([*fallback.get("sources", []), "top_changed_columns", "lineage_versions"])),
            "reasoning_summary": "Ranked columns by changed cell count between lineage version 1 and the latest approved version.",
        }

    @staticmethod
    def answer_column_impact_from_evidence(
        impact: dict[str, Any] | None,
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        if not impact:
            return fallback
        column = impact.get("column")
        task_ids = [
            task.get("task_id")
            for task in impact.get("plan_tasks") or []
            if task.get("task_id")
        ]
        worker_agents = [
            item.get("agent")
            for item in impact.get("worker_matches") or []
            if item.get("agent")
        ]
        change_columns = (impact.get("change_evidence") or {}).get("columns") or {}
        change_summary = change_columns.get(column) if isinstance(change_columns, dict) else None
        change_text = ""
        if change_summary:
            change_text = (
                f" It changed in {change_summary.get('changed_cells')} of "
                f"{change_summary.get('compared_rows')} compared rows."
            )
        answer = (
            f"Column '{column}' is "
            f"{'present' if impact.get('known_column') else 'not clearly present'} in the final dataset context."
            f"{change_text} "
            f"Related plan tasks: {', '.join(task_ids) if task_ids else 'none found'}. "
            f"Related worker outputs: {', '.join(worker_agents) if worker_agents else 'none found'}. "
            f"Within this app, downstream impact means: {', '.join(impact.get('downstream_scope') or [])}."
        )
        return {
            **fallback,
            "answer": answer,
            "sources": sorted(set([*fallback.get("sources", []), "column_impact", "execution_plan", "worker_outputs", "lineage_versions"])),
            "reasoning_summary": "Checked column references in the execution plan, worker outputs, validation artifacts, and lineage before/after evidence.",
        }

    @staticmethod
    async def answer_question_with_llm(
        report: dict[str, Any],
        question: str,
        history: list[dict[str, Any]] | None = None,
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Answer with an LLM grounded in the final report, with deterministic fallback."""
        fallback = ReportService.answer_question(report, question)
        try:
            requested_columns = ReportService.infer_requested_columns(report, question)
            question_lower = question.lower()
            asks_top_changes = any(
                token in question_lower
                for token in [
                    "most changed",
                    "changed most",
                    "thay đổi nhiều nhất",
                    "cột nào thay đổi",
                    "columns changed",
                    "top changed",
                ]
            )
            asks_impact = any(
                token in question_lower
                for token in [
                    "impact",
                    "downstream",
                    "dependency",
                    "depend",
                    "rename",
                    "đổi tên",
                    "ảnh hưởng",
                    "phụ thuộc",
                    "lien quan",
                    "liên quan",
                ]
            )
            needs_column_evidence = bool(
                requested_columns
                or any(token in question_lower for token in ["column", "cột", "before", "after", "trước", "sau", "changed", "thay đổi"])
            )
            column_evidence = None
            top_change_evidence = None
            impact_evidence = None
            if state and asks_top_changes:
                top_change_evidence = ReportService.build_top_changed_columns(state, limit=10, sample_limit=3)
                fallback = ReportService.answer_top_changes_from_evidence(top_change_evidence, fallback)
            if state and asks_impact and requested_columns:
                impact_evidence = [
                    ReportService.build_column_impact_summary(report, state, column)
                    for column in requested_columns[:5]
                ]
                if len(impact_evidence) == 1:
                    fallback = ReportService.answer_column_impact_from_evidence(impact_evidence[0], fallback)
            if state and needs_column_evidence:
                column_evidence = ReportService.build_column_change_summary(
                    state,
                    columns=requested_columns or None,
                    sample_limit=8,
                )
                fallback = ReportService.answer_column_changes_from_evidence(column_evidence, fallback)

            context = {
                "final_report": report,
                "column_change_evidence": column_evidence,
                "top_changed_columns_evidence": top_change_evidence,
                "column_impact_evidence": impact_evidence,
                "recent_chat_history": (history or [])[-10:],
            }
            llm = create_llm(temperature=0)
            messages = [
                SystemMessage(
                    content=(
                        "You are the Final Report Agent for an agentic data-cleaning pipeline. "
                        "Answer only from the provided report context. You understand the full "
                        "pipeline: upload, profiling, semantic analysis, input validation, planning, "
                        "worker execution, validation/retry, lineage promotion, metrics, exports, and "
                        "next transformations. For column impact questions, use the provided column "
                        "impact evidence and explain impact within the current data-cleaning run, not "
                        "as a dbt-wide downstream model graph. If a requested fact is missing, say it is not available "
                        "in the report instead of guessing. Do not reveal hidden chain-of-thought. "
                        "Return compact JSON with keys: answer, sources, reasoning_summary, "
                        "suggested_questions. reasoning_summary should briefly state what evidence "
                        "you checked, not private step-by-step reasoning."
                    )
                ),
                HumanMessage(
                    content=(
                        "Report context:\n"
                        f"{_compact_for_prompt(context)}\n\n"
                        f"User question: {question}"
                    )
                ),
            ]
            response = await llm.ainvoke(messages)
            raw_content = response.content if isinstance(response.content, str) else str(response.content)
            parsed = _extract_json_object(raw_content)
            if not parsed:
                return fallback

            answer = str(parsed.get("answer") or fallback["answer"]).strip()
            sources = parsed.get("sources")
            if not isinstance(sources, list) or not sources:
                sources = fallback["sources"]
            reasoning_summary = str(
                parsed.get("reasoning_summary") or "Checked the final report context and related pipeline evidence."
            ).strip()
            suggestions = parsed.get("suggested_questions")
            if not isinstance(suggestions, list) or not suggestions:
                suggestions = _suggested_questions(report)

            return {
                "answer": answer,
                "sources": [str(item) for item in sources],
                "reasoning_summary": reasoning_summary,
                "suggested_questions": [str(item) for item in suggestions[:4]],
            }
        except Exception:
            return fallback

    @staticmethod
    def list_chat_messages(run_id: str) -> list[dict[str, Any]]:
        ReportService._ensure_chat_table()
        db = SessionLocal()
        try:
            messages = db.query(ReportChatMessage).filter(
                ReportChatMessage.run_id == run_id
            ).order_by(ReportChatMessage.created_at).all()
            return [
                {
                    "id": str(message.id),
                    "run_id": message.run_id,
                    "role": message.role,
                    "content": message.content,
                    "sources": message.sources or [],
                    "reasoning_summary": (message.metadata_ or {}).get("reasoning_summary"),
                    "created_at": message.created_at.isoformat() if message.created_at else None,
                }
                for message in messages
            ]
        finally:
            db.close()

    @staticmethod
    def save_chat_message(
        run_id: str,
        role: str,
        content: str,
        sources: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ReportService._ensure_chat_table()
        db = SessionLocal()
        try:
            message = ReportChatMessage(
                run_id=run_id,
                role=role,
                content=content,
                sources=sources or [],
                metadata_=metadata or {},
            )
            db.add(message)
            db.commit()
            db.refresh(message)
            return {
                "id": str(message.id),
                "run_id": message.run_id,
                "role": message.role,
                "content": message.content,
                "sources": message.sources or [],
                "reasoning_summary": (message.metadata_ or {}).get("reasoning_summary"),
                "created_at": message.created_at.isoformat() if message.created_at else None,
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _ensure_chat_table() -> None:
        ReportChatMessage.__table__.create(bind=engine, checkfirst=True)
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE report_chat_messages ADD COLUMN IF NOT EXISTS metadata JSONB")
            )
