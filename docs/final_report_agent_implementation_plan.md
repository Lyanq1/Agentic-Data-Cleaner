# Final Report Agent Implementation Plan

> [!NOTE]
> **TL;DR - TỔNG QUAN NÂNG CẤP REPORT AGENT CHATBOT (ReAct Tool-Calling Architecture)**
>
> ### 1. Những gì đã làm & áp dụng (What was done & applied)
> - **Chuyển đổi sang ReAct Tool-Calling Agent**: Thay thế hoàn toàn cơ chế phân loại intent `if/else` chắp vá bằng mô hình Agent tự chủ có bộ công cụ chuyên biệt (LangChain Tool Binding).
> - **Tích hợp DuckDB In-Memory SQL Engine**: Bổ sung `duckdb>=1.1.0` cho phép Agent tự viết và thực thi trực tiếp các câu lệnh SQL (`SELECT`) trên các bảng Pandas DataFrames (`clean_data`, `raw_data`, `v1`, `v2`...) ngay trong bộ nhớ RAM với cơ chế zero-copy.
> - **Trang bị Bộ 4 Domain Tools chuyên biệt**:
>   1. `query_dataset_sql`: Truy vấn/thống kê/lọc/tính toán trực tiếp trên dữ liệu thô và dữ liệu đã làm sạch bằng DuckDB.
>   2. `get_evaluation_metrics`: Trích xuất chỉ số F1 Score chi tiết (TP, FP, FN, precision, recall, accuracy, cell count) & chi phí token.
>   3. `get_pipeline_telemetry`: Trích xuất rationale planner, danh sách tác vụ active/skip, log xử lý của worker & kết quả kiểm tra validation.
>   4. `get_lineage_diff`: So sánh biến động dữ liệu trước/sau theo từng cột và các phiên bản lineage.
> - **Cập nhật Giao diện Chat Frontend**: Cài đặt `react-markdown` và `remark-gfm` để render câu trả lời của Agent dưới dạng định dạng Markdown chuẩn, trực quan.
>
> ### 2. Các thay đổi chính trong mã nguồn (What was changed)
> - `pyproject.toml`: Bổ sung dependency `duckdb>=1.1.0`.
> - `app/services/report_service.py`: Tái cấu trúc `answer_question_with_llm` thành ReAct Execution Loop tự động gọi các tool thu thập chứng cứ trước khi tổng hợp câu trả lời; chuẩn hóa lề scope của class `ReportService`.
> - `frontend/src/components/views/ResultView.tsx`: Thay thế hiển thị văn bản thô bằng component `<ReactMarkdown>` hỗ trợ render Markdown.
> - `tests/test_report_react_agent.py`: Viết bộ unit test kiểm thử độc lập cho DuckDB SQL Tool và các Telemetry Tools (**PASSED 100%**).
>
> ### 3. Tại sao KHÔNG CẦN DÙNG RAG (Vector RAG)? (Why RAG is NOT needed)
> 1. **Bản chất của dữ liệu cấu trúc (Tabular Data) không hợp với Vector Search**:
>    - Vector RAG (Embedding Text Chunking) chỉ phù hợp với văn bản tự do không cấu trúc (tài liệu PDF, sách, báo). 
>    - Khi áp dụng Vector RAG vào bảng dữ liệu (Dataframe), nó không thể thực hiện các phép tính số học, gom nhóm hay truy vấn chính xác (`COUNT`, `AVG`, `SUM`, `WHERE column = x`). Dữ liệu lấy về qua vector search dễ bị mơ hồ và gây **ảo giác (hallucination)**.
>    - **Giải pháp ReAct SQL Tool vượt trội**: Cho phép LLM tự viết câu lệnh SQL để DuckDB tính toán trực tiếp trên Dataframe gốc. Kết quả trả về đạt độ chính xác **100% (Deterministic Accuracy)**.
> 2. **Pipeline Telemetry & Metrics đã được chuẩn hóa theo Schema**:
>    - Toàn bộ thông tin F1 evaluation, token cost, execution plan, worker outcomes và lineage đã được lưu trữ cấu trúc sẵn trong `GlobalState` và Database PostgreSQL.
>    - Thay vì tốn tài nguyên cắt nhỏ văn bản rồi index vào Vector DB (vừa chậm vừa tốn bộ nhớ), Agent chỉ cần gọi trực tiếp các **Domain Tools** để đọc chính xác thông tin từ hệ thống.
> 3. **Tốc độ xử lý siêu nhanh & Tiết kiệm chi phí**:
>    - Loại bỏ hoàn toàn chi phí tính Embedding Vector và hạ tầng Vector Store (ChromaDB/Pinecone).
>    - DuckDB chạy trực tiếp in-memory với độ trễ chỉ vài millisecond, giúp trải nghiệm chat phản hồi tức thì.
>
> ### 4. Các mẫu câu hỏi thực tế Report Agent có thể trả lời (Real-World Example Questions)
> - **Truy vấn & Phân tích Dữ liệu Data (via DuckDB SQL Tool)**:
>   - *"Có bao nhiêu dòng bị khuyết (null) ở cột `Address2` trong dữ liệu thô và đã được sửa thành gì trong bản cleaned?"*
>   - *"Cho tôi biết top 5 khách hàng có doanh thu (`Income`) cao nhất trong bảng dữ liệu đã được làm sạch?"*
>   - *"Thống kê số lượng bản ghi theo từng thành phố (`City`) trong tập dữ liệu sạch?"*
>   - *"Có bao nhiêu bản ghi trùng lặp đã bị xóa ở bước Deduplication?"*
> - **Đánh giá Mô hình & Chi phí (via Evaluation Metrics Tool)**:
>   - *"Cho tôi biết các chỉ số F1 Score, Precision, Recall và Accuracy của đợt làm sạch này?"*
>   - *"Có bao nhiêu ô dữ liệu được đánh giá là True Positives (TP), False Positives (FP) và False Negatives (FN)?"*
>   - *"Toàn bộ pipeline này đã tiêu tốn tổng cộng bao nhiêu LLM tokens?"*
> - **Vết thực thi Pipeline & Rationale của Agent (via Pipeline Telemetry Tool)**:
>   - *"Kế hoạch ban đầu của Planner Agent là gì và tại sao task 2 lại bị bỏ qua (skip)?"*
>   - *"Các worker `null_worker` và `typecast_worker` đã thực hiện những thay đổi gì cụ thể trên dữ liệu?"*
>   - *"Có quy tắc validation nào bị rớt (failed validation rule) ở bước kiểm tra cuối cùng không?"*
> - **Biến động dữ liệu Trước / Sau & Lineage (via Lineage Diff Tool)**:
>   - *"Những cột nào bị thay đổi nhiều nhất giữa bản thô (Version 1) và bản sạch cuối cùng?"*
>   - *"So sánh sự thay đổi về kiểu dữ liệu (dtype) và tỷ lệ null ở cột `Phone` trước và sau khi làm sạch?"*
>   - *"Cho tôi xem 3 ví dụ cụ thể về dữ liệu trước và sau khi sửa ở cột `Email`?"*

## Objective

Turn the final pipeline step from a static completion report into a post-cleaning intelligence layer. After all cleaning tasks pass validation, the Report Agent should help users understand, export, visualize, and continue working with the cleaned dataset.

## Product Positioning

Current flow:

```text
Upload data
-> Profile / Semantic analysis
-> Validate input
-> Plan
-> Execute cleaning tasks
-> Validate each task
-> Final Report Agent
```

Target final step:

```text
Final Report Agent
-> Export clean dataset
-> Export structured report
-> Export transformation / lineage diagram
-> Answer questions about the result
-> Suggest next transformations
```

The key framing is: cleaning is not the end of the workflow. It is the beginning of result understanding and downstream use.

## Current Implementation Status

Status: MVP implemented and verified.

The current implementation keeps the existing cleaning pipeline unchanged. All new behavior is attached to the final Result / Report Agent layer after the pipeline has completed or reached the report stage.

Reference inspiration:

- The design is adapted from the Cocoon/dbt lineage-based RAG idea described in the project discussion and video summary.
- The Results UI also adapts Cocoon's cleaning gallery presentation pattern: a report-like page that documents the table, exposes generated artifacts, and makes the cleaned output inspectable instead of ending at a simple success message.
- Main reference page for this UI pass: https://cocoon-data-transformation.github.io/page/clean_gallery/stg_hospital.html
- Cocoon's original domain is dbt project assistance: retrieve relevant upstream/downstream dbt models from a lineage graph instead of sending the whole project to an LLM.
- Our domain is different: a single uploaded dataset goes through a data-cleaning pipeline. Therefore, we adapt the methodology from dbt model lineage to pipeline artifact lineage.
- In this project, "lineage-aware retrieval" means retrieving pipeline-specific artifacts: dataset versions, worker outputs, validation results, metrics, report sections, and before/after column evidence.
- We intentionally do not implement vector RAG or arbitrary LLM-generated SQL at this stage, because the required evidence is structured and should be retrieved deterministically.

Implemented backend files:

- `app/services/report_service.py`
- `app/api/v1/pipeline.py`
- `app/services/lineage_service.py`
- `app/models/lineage.py`

Implemented frontend files:

- `frontend/src/api/services.ts`
- `frontend/src/components/views/ResultView.tsx`

Implemented documentation:

- `docs/final_report_agent_implementation_plan.md`

Verified checks:

- Python compile passed for the changed backend files.
- TypeScript compile passed.
- Vite production build passed.
- Vite still reports a large bundle warning, but it is non-blocking and unrelated to the Report Agent logic.

### What Is Working Now

Backend-owned final report:

- `GET /api/v1/pipeline/{run_id}/report`
- Builds the report from the current pipeline state and lineage instead of letting the frontend fake a report.
- Includes summary, profile summary, semantic summary, execution plan summary, worker outputs, validation, lineage, metrics, transformations, next actions, suggested questions, and pipeline context.

Report export:

- `GET /api/v1/pipeline/{run_id}/report/export?format=json|md|html`
- Supports JSON, Markdown, and HTML report exports.

Versioned dataset export:

- `GET /api/v1/pipeline/{run_id}/versions/{version}/download?format=csv|xlsx|parquet`
- Downloads any persisted lineage version, not only the latest cleaned dataset.
- The Result page exposes compact CSV/XLSX/Parquet buttons next to each lineage version.

Diagram export:

- `GET /api/v1/pipeline/{run_id}/diagram?type=pipeline|lineage`
- Returns Mermaid text for pipeline flow or lineage flow.

Lineage metadata retrieval:

- `LineageService.list_versions(session_id)` returns approved version metadata.
- Result UI displays lineage versions and can show the Mermaid lineage diagram.

Report chat:

- `POST /api/v1/pipeline/{run_id}/report/chat`
- `GET /api/v1/pipeline/{run_id}/report/chat`
- Chat history is stored by `run_id` in `report_chat_messages`.
- Generalized **ReAct Tool-Calling Agent** architecture replacing ad-hoc heuristic intent classification.
- Equipped with 4 domain-specific tools:
  1. `query_dataset_sql`: Runs DuckDB analytical `SELECT` queries directly on in-memory dataset tables (`clean_data`, `raw_data`, `v1`, `v2`, etc.). Can answer any query regarding values, row counts, null counts, distributions, aggregations, and row lookups.
  2. `get_evaluation_metrics`: Retrieves exact F1 score evaluation details (F1, precision, recall, accuracy, TP, FP, FN, total cells evaluated) and LLM token usage costs.
  3. `get_pipeline_telemetry`: Retrieves execution plan task rationale, active vs skipped tasks, worker execution outputs, and validation rule results.
  4. `get_lineage_diff`: Retrieves column-level or dataset-level before/after change stats, null changes, dtype changes, and sample row modifications across lineage versions.

Grounded ReAct LLM answer path:

- `ReportService.answer_question_with_llm(...)` uses the configured LLM with LangChain tool bindings.
- Tool outputs are dynamically retrieved and appended into message history before final answer synthesis.
- Hidden tool execution logs are executed behind the scenes to keep the UI clean; final answers expose source badges (`sources`) and a compact `reasoning_summary`.

Deterministic fallback:

- If the LLM fails, lacks an API key, or encounters errors during tool execution, the service gracefully falls back to deterministic answers.
- Fallback currently understands F1 score, precision, recall, accuracy, TP/FP/FN, token usage, lineage, validation, transformations, and next actions.
- This prevents broad questions such as "how many true positive" or "tốn bao nhiêu token" from falling back to a generic pipeline summary.

Before/after column evidence:

- `GET /api/v1/pipeline/{run_id}/report/columns/{column_name}/changes`
- Compares lineage version 1 against the latest approved version.
- Computes changed cell count, change rate, nulls before/after, dtype before/after, row count delta, and sample `before -> after` values.
- Report chat automatically builds this evidence when the question mentions a column or asks about before/after changes.
- The LLM receives this evidence, and fallback can also answer from it.

Before/after dataset preview:

- `GET /api/v1/pipeline/{run_id}/report/compare-preview?limit=100`
- `GET /api/v1/pipeline/{run_id}/report/compare-preview?full=true`
- `GET /api/v1/pipeline/{run_id}/report/compare-preview?before_version=1&after_version=3`
- Loads lineage version 1 and the latest approved version by default, or any requested before/after version pair.
- Returns two bounded table previews plus changed cell coordinates.
- The frontend uses the backend-provided changed cell coordinates to highlight differences without recomputing the diff in the browser.
- The Result page uses `full=true` for demo runs so users can inspect the whole uploaded file after cleaning.
- The bounded `limit` mode remains available for future pagination or very large datasets.
- Research conclusion for version comparison: because this app preserves lineage records by `session_id`, `version`, and `row_index`, the most reliable demo comparison is a deterministic row-index and column-name diff between two lineage versions. This gives changed cell coordinates, before/after values, changed counts, and column rankings without requiring vector RAG or generated SQL.

Top changed columns:

- `GET /api/v1/pipeline/{run_id}/report/changes/top?limit=10`
- Ranks columns by changed cell count between lineage version 1 and the latest approved version.
- Report chat retrieves this evidence for questions such as "which columns changed the most?" or "cột nào thay đổi nhiều nhất?"
- This maps Cocoon's targeted lineage retrieval idea to the cleaning-result domain: retrieve only the most relevant changed columns instead of sending the whole dataset.

Column impact / dependency awareness:

- `GET /api/v1/pipeline/{run_id}/report/columns/{column_name}/impact`
- Finds how a column participates in the current run's semantic profile, execution plan, worker outputs, validation artifacts, final report, lineage, exports, and Report Agent Q&A.
- Report chat retrieves this evidence for questions about impact, downstream, dependencies, rename, or "ảnh hưởng/phụ thuộc".
- This is a scoped adaptation of Cocoon's downstream dependency management. It does not claim dbt-style project-wide downstream model tracking; it explains impact inside the current cleaning pipeline run.

Frontend Report Agent workspace:

- Final Result view now uses backend-owned report data.
- The Result page is now full-width so wide datasets can be inspected more comfortably.
- The page renders dataset documentation, profile highlights, a Cocoon-inspired Cleaning Summary, validation metrics, lineage, before/after preview, Report Agent chat, recommended next actions, and exports.
- The page includes a Report JSON export button plus cleaned dataset downloads.
- The page includes a compact Report Agent evidence map covering run summary, profiling, planning, worker execution, validation approval, lineage, metrics, pipeline trace, before/after diff, and exports.
- The page shows lineage versions and auto-opens the Mermaid lineage visualization.
- The before/after comparison shows the original and cleaned dataset side by side on desktop layouts, with changed cells highlighted in both tables.
- Clicking a cell in the original table scrolls to the same row and column in the cleaned table, and clicking from cleaned scrolls back to original.
- The Ask the Report Agent panel is separated into a memoized component to avoid input lag from re-rendering the full report page.
- The Ask the Report Agent is now a compact bottom-right icon widget that can be opened or closed without taking space away from the report.
- The open widget uses a scrollable transcript with role-based message bubbles and a fixed input area at the bottom.
- The widget no longer renders suggested-question pills, leaving more room for the transcript and user input.
- Report Agent answers now visually separate the answer, source badges, and a compact evidence/analysis summary so LLM-derived analysis is easier to scan.
- Chat messages expose an `answer_mode` badge: `Backend evidence` for deterministic report/lineage/metric answers and `LLM synthesis` when the LLM is used to synthesize from bounded context.
- Out-of-scope questions, such as general knowledge questions unrelated to the current report or dataset, are rejected by a scope guard and are not sent to the LLM.
- Recommended next actions are rendered as compact bullet points so they support the report without dominating the page.
- The chat panel loads persisted history for the current `run_id`.
- While waiting for an answer, the UI shows a loading message that names the deeper evidence being checked: report, planner, workers, validation, lineage, metrics, and recent chat.
- Suggested questions are derived from the actual report context instead of being fixed generic prompts.

### Current Design Constraints

- The Report Agent does not run arbitrary SQL generated by the LLM.
- The chat is grounded through controlled report and lineage evidence.
- Chat memory is intentionally scoped to one `run_id` for demo purposes.
- Uploading or running a new dataset creates a separate chat context.
- The Report Agent reads lineage and report state, but does not modify cleaned data.
- The cleaning pipeline flow remains unchanged.
- The current "dependency" scope is pipeline/report/export scope, not a full dbt downstream model DAG.

### Remaining Improvements

- Add a column-level drilldown panel from the before/after table into detailed change evidence.
- Let the LLM generate even better suggested questions from bounded report context.
- Add explicit token/cost estimates if pricing configuration is available.
- Add tests for report generation, chat history persistence, and column diff summaries.
- If the project later supports multiple related tables or transformation graphs, add a true graph/vector RAG layer for cross-table and cross-run retrieval.

## Phase 1: Backend-Owned Final Report Contract

Move report construction from frontend heuristics into a backend-owned contract.

Report sections:

- `summary`: filename, run id, completion time, input rows, output rows, tracked columns, completed steps, retry cycles.
- `profile_summary`: initial statistical profile highlights.
- `semantic_summary`: table purpose and column-level semantic context.
- `execution_plan_summary`: tasks executed, skipped tasks, planner rationale.
- `worker_results`: deduplication, null handling, and type casting outcomes.
- `validation`: pass/fail status, failed rules, observed metrics, remaining issues.
- `lineage`: approved dataset versions, agent names, descriptions, timestamps.
- `metrics`: token metrics and F1-score evaluation when ground truth exists.
- `transformations`: readable list of applied changes.
- `next_actions`: suggested next work after cleaning.

Backend endpoints:

```text
GET /api/v1/pipeline/{run_id}/report
GET /api/v1/pipeline/{run_id}/report/export?format=json|md|html
```

Primary files:

- `app/services/report_service.py`
- `app/api/v1/pipeline.py`
- `app/graphs/nodes.py`
- `frontend/src/api/services.ts`

## Phase 2: Report Agent Backend Integration

Update `report_agent_node` so it builds or refreshes the final report after computing existing metrics.

Context sources:

- LangGraph `GlobalState`
- `execution_plan`
- `worker_outputs`
- `validation_results`
- `agent_logs`
- `token_metrics`
- `f1_metrics`
- PostgreSQL lineage versions
- latest processed dataset preview

Implementation notes:

- Keep deterministic metrics and summaries in backend services.
- Use LLM only for later explanation/Q&A, not for core counts.
- Keep the existing pipeline flow intact.

## Phase 3: Diagram Export

Add lightweight diagrams as Mermaid text first.

Diagram types:

- `pipeline`: high-level pipeline execution flow.
- `lineage`: dataset version lineage from raw input to final validated result.

Endpoint:

```text
GET /api/v1/pipeline/{run_id}/diagram?type=pipeline|lineage
```

Later enhancements can render SVG/PNG, but Mermaid text is enough for reports and documentation.

## Phase 4: Report Q&A Agent

Add a controlled chat endpoint for report/result questions.

Endpoint:

```text
POST /api/v1/pipeline/{run_id}/report/chat
```

Example request:

```json
{
  "question": "Which columns changed the most after cleaning?"
}
```

Example response:

```json
{
  "answer": "...",
  "sources": ["report", "lineage", "validation_results"],
  "suggested_questions": ["..."]
}
```

Safe retrieval tools:

- `get_report_summary(run_id)`
- `get_lineage_versions(run_id)`
- `get_validation_summary(run_id)`
- `get_worker_decisions(run_id)`
- `get_processed_preview(run_id, limit)`
- `get_column_change_summary(run_id, column)`
- `get_top_changed_columns(run_id, limit)`
- `get_column_impact_summary(run_id, column)`
- `get_next_transform_suggestions(run_id)`

Important constraint:

- Do not let the LLM run arbitrary SQL against PostgreSQL.
- Use controlled service functions and small retrieved snippets.

## Phase 5: Frontend Result Workspace

Refactor the final page into a Report Agent workspace.

Suggested UI:

```text
Final Report Agent

[Download Dataset] [Export Report] [Export Diagram]

Tabs:
- Summary
- Transformations
- Validation
- Lineage
- Ask
```

Initial suggested questions:

- What changed after cleaning?
- Which agent changed the dataset?
- Were there any remaining validation issues?
- Which columns were affected the most?
- What should I transform next?

Primary files:

- `frontend/src/components/views/ResultView.tsx`
- `frontend/src/api/services.ts`

## Phase 6: Suggested Next Transform

Generate practical next-step recommendations from the final report:

- Standardize categorical values.
- Normalize strings or identifiers.
- Add stricter validation rules.
- Map to a target schema.
- Create derived features.
- Build a searchable catalog if multiple cleaned tables are available.

These should be recommendations only at first. A later phase can convert a suggestion into a new execution plan.

## MVP Scope

Recommended implementation order:

1. Add backend `ReportService`.
2. Add `/report` endpoint.
3. Add report export as JSON and Markdown.
4. Add Mermaid pipeline and lineage diagram endpoint.
5. Update frontend `getReport()` to use backend report.
6. Add visible export actions in `ResultView`.
7. Add Q&A endpoint and frontend chat tab after the report contract is stable.

## Success Criteria

- The final page no longer constructs a fake report only on the frontend.
- The backend report includes data lineage, validation, worker decisions, and metrics.
- Users can export a readable report.
- Users can inspect a diagram of how the dataset reached its final version.
- Users can inspect the original and cleaned dataset side by side and see changed cells.
- The architecture is ready for grounded Report Q&A without arbitrary database access.

Current status against success criteria:

- Backend-owned report: done.
- Data lineage, validation, worker decisions, and metrics in report: done.
- Report export: done for JSON, Markdown, and HTML.
- Diagram inspection: done as auto-opened Mermaid visualization in the Result page.
- Grounded Report Q&A without arbitrary DB access: done as an MVP.
- Before/after column change evidence: done as an MVP.
- Before/after dataset preview UI: done as an MVP.
- Cocoon-inspired lineage-aware targeted retrieval: done as an MVP for report, lineage, top changed columns, and scoped column impact.
