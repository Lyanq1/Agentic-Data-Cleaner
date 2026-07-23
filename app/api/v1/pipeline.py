"""Pipeline API — upload dataset, run pipeline, check state."""
import copy
import io
import json
import re
import uuid
import logging
from typing import Any

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage

from app.exceptions.ingestion_exceptions import IngestionError
from app.services.dataframe_order import restore_original_column_order
from app.services.lineage_service import LineageService
from app.services.lineage_utils import resolve_lineage_session_id
from app.services.report_service import ReportService
from app.services.ingestion import get_ingestion_service
from app.services.pipeline import run_pipeline, get_pipeline_state
from app.graphs.utils import _load_dataframe
from app.graphs.graph import build_graph
from app.graphs.checkpointer import get_checkpointer_manager
from app.graphs.states.planning import DedupStrategy, ExecutionPlan

logger = logging.getLogger(__name__)
router = APIRouter()


class ReportChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


@router.post("/pipeline/run", summary="Upload dataset and run the cleaning pipeline")
async def api_run_pipeline(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Dataset file (CSV, TSV, Excel, JSON, JSONL)"),
    clean_file: UploadFile | None = File(None, description="Optional ground truth file for testing"),
    user_prompt: str = Form(default="", description="Optional cleaning instruction"),
):
    """Upload a dataset, convert to canonical Parquet, then run profiler → input_validator.

    Returns a ``run_id`` that can be used to check state later via ``GET /pipeline/{run_id}/state``.
    """
    contents = await file.read()

    # Ingestion: validate → save → convert to Parquet
    ingestion = get_ingestion_service()
    try:
        ingestion.validate(file.filename, contents)
        result = ingestion.save_and_convert(file.filename, contents)
    except IngestionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    clean_dataset_path = None
    if clean_file:
        clean_contents = await clean_file.read()
        try:
            ingestion.validate(clean_file.filename, clean_contents)
            # Write directly to disk to avoid bottlenecking the process with parsing
            from app.config.config import get_settings
            from pathlib import Path
            upload_dir = Path(get_settings().upload_dir)
            upload_dir.mkdir(parents=True, exist_ok=True)
            clean_path = upload_dir / f"clean_{clean_file.filename}"
            clean_path.write_bytes(clean_contents)
            clean_dataset_path = str(clean_path)
        except IngestionError as e:
            logger.warning(f"Failed to process clean file: {e}")

    # Run pipeline in background
    run_id = uuid.uuid4().hex[:12]
    background_tasks.add_task(
        run_pipeline,
        run_id=run_id,
        canonical_path=result.canonical_path,
        input_format=result.input_format,
        user_prompt=user_prompt,
        original_filename=result.original_filename,
        data_schema=result.data_schema,
        clean_dataset_path=clean_dataset_path,
    )

    return {
        "run_id": run_id,
        "message": "Pipeline execution started in the background.",
        "original_filename": result.original_filename,
        "input_format": result.input_format,
        "canonical_path": result.canonical_path,
    }


@router.get("/pipeline/{run_id}/state", summary="Get current state of a pipeline run")
async def api_get_pipeline_state(run_id: str):
    """Retrieve the current state of a pipeline run by its ``run_id``.

    Reads directly from the Postgres checkpointer — reflects the latest snapshot.
    """
    try:
        state = await get_pipeline_state(run_id)
    except Exception as e:
        logger.error(f"Failed to retrieve state for run_id={run_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve state: {e}")

    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    return state


def _load_latest_processed_dataframe(state: dict):
    """Load the latest processed dataframe from lineage, falling back to canonical parquet."""
    session_id = resolve_lineage_session_id(state)
    if session_id:
        df = LineageService.get_latest_version(session_id)
        if not df.empty:
            return restore_original_column_order(df, state)

    for key in ["physical_dataframe_path", "dataset_path"]:
        candidate_path = state.get(key)
        if not candidate_path:
            continue
        try:
            return _load_dataframe(candidate_path)
        except Exception:
            continue

    return None


def _json_safe_preview_value(value):
    """Convert dataframe preview values to JSON-safe scalars."""
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe_preview_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe_preview_value(item) for item in value]
    return value


@router.get("/pipeline/{run_id}/download", summary="Download latest processed dataset")
async def api_download_processed_dataset(run_id: str, format: str = "parquet"):
    """Export the latest processed lineage version as CSV, XLSX, or Parquet."""
    state = await get_pipeline_state(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    try:
        df = _load_latest_processed_dataframe(state)
    except Exception as e:
        logger.error(f"Failed to load processed dataset for run_id={run_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load processed dataset: {e}")

    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="No processed dataset available to download.")

    export_format = format.lower()
    if export_format not in {"csv", "xlsx", "parquet"}:
        raise HTTPException(status_code=400, detail="Unsupported format. Use csv, xlsx, or parquet.")

    buffer = io.BytesIO()
    try:
        if export_format == "csv":
            buffer.write(df.to_csv(index=False).encode("utf-8-sig"))
            media_type = "text/csv"
            extension = "csv"
        elif export_format == "xlsx":
            df.to_excel(buffer, index=False, engine="openpyxl")
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            extension = "xlsx"
        else:
            df.to_parquet(buffer, index=False, engine="pyarrow")
            media_type = "application/octet-stream"
            extension = "parquet"
    except Exception as e:
        logger.error(f"Failed to export processed dataset for run_id={run_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to export processed dataset: {e}")
    buffer.seek(0)

    filename = f"{run_id}_processed.{extension}"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(buffer, media_type=media_type, headers=headers)


@router.get("/pipeline/{run_id}/preview", summary="Preview latest processed dataset")
async def api_preview_processed_dataset(run_id: str, limit: int = 50):
    """Return a small JSON preview of the latest processed lineage version."""
    state = await get_pipeline_state(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    try:
        df = _load_latest_processed_dataframe(state)
    except Exception as e:
        logger.error(f"Failed to load processed preview for run_id={run_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load processed preview: {e}")

    if df is None or df.empty:
        return {
            "columns": [],
            "rows": [],
            "row_count": 0,
            "preview_count": 0,
        }

    safe_limit = max(1, min(limit, 1000))
    preview_df = df.head(safe_limit).where(df.head(safe_limit).notna(), None)
    rows = [
        {str(key): _json_safe_preview_value(value) for key, value in row.items()}
        for row in preview_df.to_dict(orient="records")
    ]
    return {
        "columns": [str(col) for col in df.columns],
        "rows": rows,
        "row_count": int(len(df)),
        "preview_count": int(len(preview_df)),
    }


async def _build_final_report_or_404(run_id: str) -> dict[str, Any]:
    state = await get_pipeline_state(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    try:
        return ReportService.build_report(run_id, state)
    except Exception as e:
        logger.error(f"Failed to build final report for run_id={run_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to build final report: {e}") from e


@router.get("/pipeline/{run_id}/report", summary="Get final Report Agent artifact")
async def api_get_final_report(run_id: str):
    """Return the backend-owned final report for a completed or in-progress run."""
    return await _build_final_report_or_404(run_id)


@router.get("/pipeline/{run_id}/report/columns/{column_name}/changes", summary="Get before/after change evidence for a column")
async def api_get_column_change_summary(run_id: str, column_name: str):
    """Return deterministic before/after evidence for one column using lineage versions."""
    state = await get_pipeline_state(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    evidence = ReportService.build_column_change_summary(state, columns=[column_name])
    if evidence.get("available") and not evidence.get("columns"):
        raise HTTPException(status_code=404, detail=f"Column '{column_name}' was not found in before/after lineage versions.")
    return evidence


@router.get("/pipeline/{run_id}/report/compare-preview", summary="Preview before/after dataset changes")
async def api_get_dataset_compare_preview(run_id: str, limit: int = 100, full: bool = False):
    """Return side-by-side before/after preview rows with changed cell coordinates."""
    state = await get_pipeline_state(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    safe_limit = None if full else max(1, min(limit, 500))
    return ReportService.build_dataset_compare_preview(state, limit=safe_limit)


@router.get("/pipeline/{run_id}/report/changes/top", summary="Get columns with the most before/after changes")
async def api_get_top_changed_columns(run_id: str, limit: int = 10):
    """Return top changed columns using lineage version 1 vs latest approved version."""
    state = await get_pipeline_state(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    return ReportService.build_top_changed_columns(state, limit=max(1, min(limit, 50)))


@router.get("/pipeline/{run_id}/report/columns/{column_name}/impact", summary="Get column impact within the current pipeline run")
async def api_get_column_impact_summary(run_id: str, column_name: str):
    """Return lineage-aware column impact for the current report/pipeline scope."""
    state = await get_pipeline_state(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    report = ReportService.build_report(run_id, state)
    impact = ReportService.build_column_impact_summary(report, state, column_name)
    if not impact.get("known_column"):
        raise HTTPException(status_code=404, detail=f"Column '{column_name}' was not found in the report context.")
    return impact


@router.get("/pipeline/{run_id}/report/export", summary="Export final report")
async def api_export_final_report(run_id: str, format: str = "json"):
    """Export the final report as JSON, Markdown, or HTML."""
    report = await _build_final_report_or_404(run_id)
    export_format = format.lower()

    if export_format == "json":
        content = json.dumps(report, ensure_ascii=False, indent=2)
        media_type = "application/json"
        extension = "json"
    elif export_format in {"md", "markdown"}:
        content = ReportService.render_markdown(report)
        media_type = "text/markdown; charset=utf-8"
        extension = "md"
    elif export_format == "html":
        content = ReportService.render_html(report)
        media_type = "text/html; charset=utf-8"
        extension = "html"
    else:
        raise HTTPException(status_code=400, detail="Unsupported report format. Use json, md, or html.")

    headers = {"Content-Disposition": f'attachment; filename="{run_id}_final_report.{extension}"'}
    return Response(content=content, media_type=media_type, headers=headers)


@router.get("/pipeline/{run_id}/diagram", summary="Export Report Agent diagram as Mermaid")
async def api_get_report_diagram(run_id: str, type: str = "lineage"):
    """Return a Mermaid diagram for the pipeline or data lineage."""
    report = await _build_final_report_or_404(run_id)
    diagram_type = type.lower()
    if diagram_type == "pipeline":
        diagram = ReportService.build_pipeline_diagram(report)
    elif diagram_type == "lineage":
        diagram = ReportService.build_lineage_diagram(report)
    else:
        raise HTTPException(status_code=400, detail="Unsupported diagram type. Use pipeline or lineage.")
    return {
        "run_id": run_id,
        "type": diagram_type,
        "format": "mermaid",
        "diagram": diagram,
    }


@router.post("/pipeline/{run_id}/report/chat", summary="Ask a grounded question about the final report")
async def api_chat_with_report(run_id: str, request: ReportChatRequest):
    """Answer report questions using controlled report, lineage, and validation context."""
    state = await get_pipeline_state(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    report = ReportService.build_report(run_id, state)
    history_before = ReportService.list_chat_messages(run_id)
    ReportService.save_chat_message(run_id, "user", request.question)
    answer = await ReportService.answer_question_with_llm(report, request.question, history_before, state)
    assistant_message = ReportService.save_chat_message(
        run_id,
        "assistant",
        answer["answer"],
        sources=answer.get("sources", []),
        metadata={"reasoning_summary": answer.get("reasoning_summary")},
    )
    return {
        **answer,
        "message": assistant_message,
        "history": ReportService.list_chat_messages(run_id),
    }


@router.get("/pipeline/{run_id}/report/chat", summary="Get Report Agent chat history")
async def api_get_report_chat_history(run_id: str):
    """Return persisted Report Agent chat history for a pipeline run."""
    state = await get_pipeline_state(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    return {
        "run_id": run_id,
        "messages": ReportService.list_chat_messages(run_id),
    }


class ResolveRequest(BaseModel):
    answers: dict[str, str]


class ApproveDedupReview(BaseModel):
    key_columns: list[str] | None = None
    identifier_columns: list[str] | None = None
    ignored_columns: list[str] | None = None
    keep_rule: str | None = None


class ApproveNullStrategySelection(BaseModel):
    strategy: str
    fill_value: Any | None = None
    allow_pattern_mismatch: bool = False
    allow_dmv_sentinel: bool = False


class ApproveNullReview(BaseModel):
    strategies: dict[str, str | ApproveNullStrategySelection] = Field(default_factory=dict)


class ApprovePlanRequest(BaseModel):
    note: str | None = None
    dedup_review: ApproveDedupReview | None = None
    null_review: ApproveNullReview | None = None


def _dedupe_columns(columns: list[str] | None) -> list[str]:
    if not columns:
        return []
    seen: set[str] = set()
    ordered: list[str] = []
    for column in columns:
        if column not in seen:
            ordered.append(column)
            seen.add(column)
    return ordered


def _validate_review_columns(columns: list[str], dataset_schema: dict[str, Any] | None, field_name: str) -> None:
    if not dataset_schema:
        return
    missing = [column for column in columns if column not in dataset_schema]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown columns in dedup_review.{field_name}: {missing}",
        )


def _apply_dedup_review_override(
    execution_plan: Any,
    dedup_review: ApproveDedupReview,
    dataset_schema: dict[str, Any] | None,
) -> ExecutionPlan:
    plan = ExecutionPlan.model_validate(execution_plan)

    key_columns = _dedupe_columns(dedup_review.key_columns)
    identifier_columns = _dedupe_columns(dedup_review.identifier_columns)
    ignored_columns = _dedupe_columns(dedup_review.ignored_columns)
    keep_rule = dedup_review.keep_rule

    _validate_review_columns(key_columns, dataset_schema, "key_columns")
    _validate_review_columns(identifier_columns, dataset_schema, "identifier_columns")
    _validate_review_columns(ignored_columns, dataset_schema, "ignored_columns")
    if keep_rule is not None and keep_rule not in {"keep_most_complete", "keep_first", "keep_last"}:
        raise HTTPException(
            status_code=400,
            detail="dedup_review.keep_rule must be one of keep_most_complete, keep_first, keep_last.",
        )

    updated_task = False
    for wrapper in plan.task_list:
        task = wrapper.work_order
        if task.task_id != "deduplication":
            continue

        strategy: dict[str, Any] = {}
        if task.strategy is not None:
            if hasattr(task.strategy, "model_dump"):
                strategy = task.strategy.model_dump()
            elif hasattr(task.strategy, "dict"):
                strategy = task.strategy.dict()
            elif isinstance(task.strategy, dict):
                strategy = copy.deepcopy(task.strategy)

        if dedup_review.key_columns is not None:
            strategy["primary_keys"] = key_columns
            task.columns = key_columns
        if dedup_review.identifier_columns is not None:
            strategy["identifier_columns"] = identifier_columns
        if dedup_review.ignored_columns is not None:
            strategy["ignored_columns"] = ignored_columns
        if keep_rule is not None:
            strategy["keep_rule"] = keep_rule

        effective_keys = [
            column for column in strategy.get("primary_keys", []) if column not in set(strategy.get("ignored_columns", []))
        ]
        strategy["dedup_scope"] = "key_level" if effective_keys else "row_level"
        strategy["duplicate_types"] = ["duplicate_key"] if effective_keys else ["exact_row"]
        strategy["exact_match"] = {"enabled": not bool(effective_keys)}
        strategy["key_based"] = {
            **(strategy.get("key_based") if isinstance(strategy.get("key_based"), dict) else {}),
            "keys": effective_keys,
            "survivor_policy": {"fallback": "first" if strategy.get("keep_rule") == "keep_first" else "last" if strategy.get("keep_rule") == "keep_last" else "most_complete"},
        }
        strategy.setdefault("normalization", {})
        strategy.setdefault("fuzzy_matching", {})
        strategy.setdefault("llm_review", {})
        strategy.setdefault("output_artifacts", {})

        task.skip = False
        task.skip_reason = None
        task.rationale = "Approved through planner HITL override."
        task.strategy = DedupStrategy.model_validate(strategy)
        updated_task = True
        break

    if not updated_task:
        raise HTTPException(status_code=400, detail="No deduplication task exists in the execution plan.")

    if plan.review is not None:
        for section in plan.review.sections:
            if section.task_id != "deduplication":
                continue
            for field in section.fields:
                if field.field_key == "mode":
                    field.value = "exact_key" if key_columns else "exact_full_row"
                if field.field_key == "key_columns" and dedup_review.key_columns is not None:
                    field.value = key_columns
                elif field.field_key == "identifier_columns" and dedup_review.identifier_columns is not None:
                    field.value = identifier_columns
                elif field.field_key == "ignored_columns" and dedup_review.ignored_columns is not None:
                    field.value = ignored_columns
                elif field.field_key == "keep_rule" and keep_rule is not None:
                    field.value = keep_rule
            break
        plan.review.warnings = [
            warning for warning in plan.review.warnings
            if "No duplicate rows or key-level duplicates detected" not in warning
        ]

    if "Deduplication is skipped" in plan.plan_summary or "Deduplication is skipped as no duplicate rows or key-level duplicates are detected." in plan.plan_summary:
        plan.plan_summary = (
            "The cleaning plan includes planner-approved deduplication, followed by "
            "type casting and null handling."
        )
    return plan


def _active_task_list_from_plan(plan: ExecutionPlan) -> list[str]:
    ordered_task_ids = ["deduplication", "type_casting", "null_handling"]
    active = {
        wrapper.work_order.task_id
        for wrapper in plan.task_list
        if not wrapper.work_order.skip
    }
    return [task_id for task_id in ordered_task_ids if task_id in active]


def _apply_null_review_override(
    execution_plan: Any, null_review: ApproveNullReview
) -> ExecutionPlan:
    plan = ExecutionPlan.model_validate(execution_plan)
    offered: dict[str, set[str]] = {}
    review_metadata: dict[str, dict[str, Any]] = {}
    if plan.review is not None:
        for section in plan.review.sections:
            if section.task_id != "null_handling":
                continue
            for field in section.fields:
                if field.field_key.startswith("strategy."):
                    column = field.field_key[len("strategy."):]
                    offered[column] = set(field.options)
                    review_metadata[column] = dict(field.metadata or {})

    task = next(
        (
            wrapper.work_order
            for wrapper in plan.task_list
            if wrapper.work_order.task_id == "null_handling"
        ),
        None,
    )
    if task is None:
        raise HTTPException(status_code=400, detail="No null handling task exists in the plan.")
    strategy = task.strategy.model_dump() if hasattr(task.strategy, "model_dump") else copy.deepcopy(task.strategy or {})
    per_column = strategy.get("per_column") or {}

    missing_decisions = set(offered) - set(null_review.strategies)
    if missing_decisions:
        raise HTTPException(
            status_code=400,
            detail=f"Missing null strategy review decisions for columns: {sorted(missing_decisions)}",
        )

    for column, raw_selection in null_review.strategies.items():
        if isinstance(raw_selection, str):
            selected = raw_selection
            selected_fill_value = per_column.get(column, {}).get("fill_value")
            allow_pattern_mismatch = False
            allow_dmv_sentinel = False
        else:
            selected = raw_selection.strategy
            selected_fill_value = raw_selection.fill_value
            allow_pattern_mismatch = raw_selection.allow_pattern_mismatch
            allow_dmv_sentinel = raw_selection.allow_dmv_sentinel
        if column not in offered or selected not in offered[column]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid null strategy review selection for column '{column}'.",
            )
        if column not in per_column:
            raise HTTPException(status_code=400, detail=f"Unknown null strategy column '{column}'.")
        if selected == "fill_value" and selected_fill_value is None:
            raise HTTPException(
                status_code=400,
                detail=f"fill_value requires a constant for column '{column}'.",
            )
        validation_overrides: dict[str, Any] = {}
        if selected == "fill_value":
            metadata = review_metadata.get(column, {})
            pattern = metadata.get("expected_str_pattern")
            pattern_mismatch = False
            if pattern:
                try:
                    pattern_mismatch = re.match(
                        str(pattern), str(selected_fill_value).strip()
                    ) is None
                except re.error as exc:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid expected string pattern for column '{column}': {exc}",
                    ) from exc
            potential_dmv = metadata.get("potential_dmv") or []
            dmv_mismatch = selected_fill_value in potential_dmv
            if pattern_mismatch and not allow_pattern_mismatch:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"fill_value for column '{column}' does not match the expected string "
                        "pattern; explicit acknowledgement is required."
                    ),
                )
            if dmv_mismatch and not allow_dmv_sentinel:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"fill_value for column '{column}' is a potential disguised missing "
                        "value; explicit acknowledgement is required."
                    ),
                )
            if pattern_mismatch:
                validation_overrides["expected_str_pattern"] = {
                    "allow_fill_value_mismatch": True,
                    "acknowledged_value": selected_fill_value,
                    "acknowledged_by_user": True,
                }
            if dmv_mismatch:
                validation_overrides["potential_dmv"] = {
                    "allow_fill_value_as_sentinel": True,
                    "acknowledged_value": selected_fill_value,
                    "acknowledged_by_user": True,
                }
        per_column[column]["strategy"] = selected
        per_column[column]["fill_value"] = (
            selected_fill_value if selected == "fill_value" else None
        )
        per_column[column]["validation_overrides"] = validation_overrides
        if plan.review is not None:
            for section in plan.review.sections:
                for field in section.fields:
                    if field.field_key == f"strategy.{column}":
                        field.value = selected

    strategy["per_column"] = per_column
    task.strategy = strategy
    return plan


@router.post("/pipeline/{run_id}/resolve", summary="Submit clarification answers and resume pipeline")
async def api_resolve_pipeline(
    run_id: str,
    payload: ResolveRequest,
    background_tasks: BackgroundTasks,
):
    """Update checkpointer state with user's answers and resume the cleaning pipeline."""
    config = {"configurable": {"thread_id": run_id}}
    
    async with get_checkpointer_manager().get() as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        snapshot = await graph.aget_state(config)
        
        if not snapshot or not snapshot.values:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
        
        state = snapshot.values
        val_result = state.get("input_validation_result")
        if not val_result:
            raise HTTPException(status_code=400, detail="No input validation result found to resolve.")
            
        # Convert val_result to dict if it is a Pydantic model or other object
        if hasattr(val_result, "model_dump"):
            val_result_dict = val_result.model_dump()
        elif hasattr(val_result, "dict"):
            val_result_dict = val_result.dict()
        else:
            val_result_dict = dict(val_result)
            
        clarifications = val_result_dict.get("clarifications")
        if not clarifications:
            raise HTTPException(status_code=400, detail="No clarifications found in input validation result.")
            
        # Update the answer field in clarifications
        # payload.answers is e.g. {"null.Q1_strategy": "Option A: ...", ...}
        cleaned_answers = {}
        for key, answer in payload.answers.items():
            parts = key.split(".")
            if len(parts) == 2:
                cat, q_key = parts
                cat_data = clarifications.get(cat)
                if cat_data:
                    q_data = cat_data.get(q_key)
                    if q_data:
                        cleaned_answer = answer
                        if q_key.startswith("Q2_strategy_column_") and answer:
                            col_name = q_key[len("Q2_strategy_column_"):]
                            # Check column expected type
                            expected_type = "str"
                            sem_profile = state.get("semantic_profile")
                            if sem_profile:
                                if hasattr(sem_profile, "columns"):
                                    col_detail = sem_profile.columns.get(col_name)
                                    if col_detail:
                                        expected_type = getattr(col_detail, "expected_type", "str")
                                elif isinstance(sem_profile, dict) and "columns" in sem_profile:
                                    col_detail = sem_profile["columns"].get(col_name)
                                    if col_detail:
                                        expected_type = col_detail.get("expected_type", "str")
                            
                            if expected_type in ("datetime", "date") and not answer.lower().startswith("keep_null"):
                                # Parse and convert to ISO format
                                prefix = ""
                                ans_stripped = answer.strip()
                                while True:
                                    matched = False
                                    lower_ans = ans_stripped.lower()
                                    for p in ["custom strategy:", "fill_value:", "fill_value ", "fill ", "impute "]:
                                        if lower_ans.startswith(p):
                                            idx = len(p)
                                            prefix += ans_stripped[:idx]
                                            ans_stripped = ans_stripped[idx:].strip()
                                            matched = True
                                            break
                                    if not matched:
                                        break
                                
                                from dateutil import parser
                                try:
                                    dt = parser.parse(ans_stripped, dayfirst=True)
                                    if expected_type == "date":
                                        iso_val = dt.date().isoformat()
                                    else:
                                        iso_val = dt.isoformat()
                                    cleaned_answer = f"{prefix}{iso_val}"
                                except Exception:
                                    pass
                        
                        q_data["answer"] = cleaned_answer
                        cleaned_answers[key] = cleaned_answer
            if key not in cleaned_answers:
                cleaned_answers[key] = answer
        
        # Treat fully answered clarification payloads as ready for planner consumption.
        # The planner already reads the answered clarification structure directly.
        val_result_dict["status"] = "ready"
        val_result_dict["reasoning"] = (
            "User provided clarification answers; planner can proceed using the "
            "resolved clarification payload."
        )

        # Build HumanMessage summarizing answers for the LLM chat history
        summary_lines = ["Here are my decisions for the clarification questions:"]
        for key, answer in cleaned_answers.items():
            summary_lines.append(f"- {key}: {answer}")
        summary_msg = HumanMessage(content="\n".join(summary_lines))
        
        # Prepare state updates
        state_updates = {
            "input_validation_result": val_result_dict,
            "messages": [summary_msg],
            "next_node": "planner",
        }
        
        # Update the thread state in checkpointer
        await graph.aupdate_state(
            snapshot.config if getattr(snapshot, "config", None) else config,
            state_updates,
            as_node="input_validator",
        )
        
    # Resume the existing checkpointed graph state in the background.
    # Do not restart via run_pipeline(), because this thread already has
    # persisted state and should continue from planner after input validation.
    async def resume_graph():
        from app.core.websocket_manager import manager
        import time
        async with get_checkpointer_manager().get() as cp:
            gr = build_graph(checkpointer=cp)
            try:
                async for event in gr.astream_events(None, config=config, version="v2"):
                    kind = event["event"]
                    name = event.get("name", "")

                    if kind == "on_tool_start":
                        await manager.broadcast_to_run(run_id, {"event": "log", "log": {"timestamp": time.time(), "agent": name, "message": f"Calling tool '{name}'...", "level": "info"}})
                    elif kind == "on_tool_end":
                        await manager.broadcast_to_run(run_id, {"event": "log", "log": {"timestamp": time.time(), "agent": name, "message": f"Tool '{name}' completed successfully.", "level": "info"}})
                    elif kind == "on_tool_error":
                        err = event.get("data", {}).get("error", "Unknown error")
                        await manager.broadcast_to_run(run_id, {"event": "log", "log": {"timestamp": time.time(), "agent": name, "message": f"Tool '{name}' failed. Error: {err}", "level": "error"}})
                    elif kind == "on_chain_start":
                        if name in ["profiler", "semantic_profile", "input_validator", "planner", "supervisor", "deduplication", "null_handling", "type_casting", "validator", "report_agent"]:
                            await manager.broadcast_to_run(run_id, {"event": "log", "log": {"timestamp": time.time(), "agent": "system", "message": f"Starting step: {name}", "level": "info"}})
                    elif kind == "on_chain_error":
                        err = event.get("data", {}).get("error", "Unknown error")
                        if name != "LangGraph":
                            await manager.broadcast_to_run(run_id, {"event": "log", "log": {"timestamp": time.time(), "agent": "system", "message": f"Error in {name}: {err}", "level": "error"}})

                snapshot_after = await gr.aget_state(config)
                if snapshot_after and snapshot_after.next:
                    await manager.broadcast_to_run(run_id, {"event": "status_change", "status": "paused"})
                else:
                    await manager.broadcast_to_run(run_id, {"event": "status_change", "status": "completed"})
            except Exception as e:
                logger.error(f"Pipeline resume after resolve error: {e}")
                await manager.broadcast_to_run(run_id, {"event": "status_change", "status": "failed"})

    background_tasks.add_task(resume_graph)
    
    return {
        "message": "Answers submitted and pipeline resume triggered successfully."
    }


@router.post("/pipeline/{run_id}/approve_plan", summary="Approve execution plan and resume cleaning pipeline")
async def api_approve_plan(
    run_id: str,
    background_tasks: BackgroundTasks,
    payload: ApprovePlanRequest | None = None,
):
    """Resume the pipeline from the plan-approval checkpoint."""
    config = {"configurable": {"thread_id": run_id}}
    
    async with get_checkpointer_manager().get() as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        snapshot = await graph.aget_state(config)
        
        if not snapshot or not snapshot.values:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

        state = snapshot.values
        execution_plan = state.get("execution_plan")
        review = None
        if execution_plan is not None:
            if hasattr(execution_plan, "review"):
                review = execution_plan.review
            elif isinstance(execution_plan, dict):
                review = execution_plan.get("review")

        if review is None:
            raise HTTPException(status_code=400, detail="No pending execution plan review is available for this run.")

        updated_plan = execution_plan
        updated_task_list = state.get("task_list", [])
        null_review_required = False
        if review is not None:
            sections = review.sections if hasattr(review, "sections") else review.get("sections", [])
            null_review_required = any(
                (section.task_id if hasattr(section, "task_id") else section.get("task_id"))
                == "null_handling"
                for section in sections
            )
        if null_review_required and (payload is None or payload.null_review is None):
            raise HTTPException(
                status_code=400,
                detail="Null strategy compatibility decisions are required before execution.",
            )
        if payload and payload.dedup_review is not None:
            updated_plan = _apply_dedup_review_override(
                execution_plan=execution_plan,
                dedup_review=payload.dedup_review,
                dataset_schema=state.get("dataset_schema"),
            )
            updated_task_list = _active_task_list_from_plan(updated_plan)
        if payload and payload.null_review is not None:
            updated_plan = _apply_null_review_override(updated_plan, payload.null_review)
            updated_task_list = _active_task_list_from_plan(updated_plan)

        approval_updates = {
            "execution_plan": updated_plan,
            "task_list": updated_task_list,
            "current_task_idx": 0,
            "hitl_status": "approved",
            "messages": [HumanMessage(content=payload.note)] if payload and payload.note else [],
        }
        await graph.aupdate_state(snapshot.config if getattr(snapshot, "config", None) else config, approval_updates, as_node="planner")
            
    # Resume graph execution in the background
    async def resume_graph():
        from app.core.websocket_manager import manager
        import time
        async with get_checkpointer_manager().get() as cp:
            gr = build_graph(checkpointer=cp, interrupt_before=[])
            try:
                async for event in gr.astream_events(None, config=config, version="v2"):
                    kind = event["event"]
                    name = event.get("name", "")
                    
                    if kind == "on_tool_start":
                        await manager.broadcast_to_run(run_id, {"event": "log", "log": {"timestamp": time.time(), "agent": name, "message": f"Calling tool '{name}'...", "level": "info"}})
                    elif kind == "on_tool_end":
                        await manager.broadcast_to_run(run_id, {"event": "log", "log": {"timestamp": time.time(), "agent": name, "message": f"Tool '{name}' completed successfully.", "level": "info"}})
                    elif kind == "on_tool_error":
                        err = event.get("data", {}).get("error", "Unknown error")
                        await manager.broadcast_to_run(run_id, {"event": "log", "log": {"timestamp": time.time(), "agent": name, "message": f"Tool '{name}' failed. Error: {err}", "level": "error"}})
                    elif kind == "on_chain_start":
                        if name in ["profiler", "semantic_profile", "input_validator", "planner", "supervisor", "deduplication", "null_handling", "type_casting", "validator", "report_agent"]:
                            await manager.broadcast_to_run(run_id, {"event": "log", "log": {"timestamp": time.time(), "agent": "system", "message": f"Starting step: {name}", "level": "info"}})
                    elif kind == "on_chain_error":
                        err = event.get("data", {}).get("error", "Unknown error")
                        if name != "LangGraph":
                            await manager.broadcast_to_run(run_id, {"event": "log", "log": {"timestamp": time.time(), "agent": "system", "message": f"Error in {name}: {err}", "level": "error"}})
                
                await manager.broadcast_to_run(run_id, {"event": "status_change", "status": "completed"})
            except Exception as e:
                logger.error(f"Pipeline resume error: {e}")
                await manager.broadcast_to_run(run_id, {"event": "status_change", "status": "failed"})
            
    background_tasks.add_task(resume_graph)
    
    return {
        "message": "Plan approved, pipeline execution resumed."
    }


@router.post("/pipeline/benchmark_run", summary="Upload dataset and run benchmark cleaning pipeline against ground truth")
async def api_benchmark_run_pipeline(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Dataset file (CSV, TSV, Excel, JSON, JSONL)"),
    clean_file: UploadFile = File(..., description="Required ground truth file for testing"),
):
    """Upload a dataset and ground truth, then run profiler → input_validator → planner → workers → report_agent.
    All clarifications are auto-resolved against the ground truth, and F1-score is calculated at the end.
    """
    contents = await file.read()

    # Ingestion: validate → save → convert to Parquet
    ingestion = get_ingestion_service()
    try:
        ingestion.validate(file.filename, contents)
        result = ingestion.save_and_convert(file.filename, contents)
    except IngestionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    clean_contents = await clean_file.read()
    try:
        ingestion.validate(clean_file.filename, clean_contents)
        # Write directly to disk
        from app.config.config import get_settings
        from pathlib import Path
        upload_dir = Path(get_settings().upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        clean_path = upload_dir / f"clean_{clean_file.filename}"
        clean_path.write_bytes(clean_contents)
        clean_dataset_path = str(clean_path)
    except IngestionError as e:
        raise HTTPException(status_code=400, detail=f"Failed to process clean file: {e}")

    # Run pipeline in background with pipeline_mode="benchmark"
    run_id = uuid.uuid4().hex[:12]
    background_tasks.add_task(
        run_pipeline,
        run_id=run_id,
        canonical_path=result.canonical_path,
        input_format=result.input_format,
        user_prompt="",
        original_filename=result.original_filename,
        data_schema=result.data_schema,
        clean_dataset_path=clean_dataset_path,
        pipeline_mode="benchmark",
    )

    return {
        "run_id": run_id,
        "message": "Benchmark pipeline execution started in the background.",
        "original_filename": result.original_filename,
        "input_format": result.input_format,
        "canonical_path": result.canonical_path,
        "ground_truth_path": clean_dataset_path,
    }
