# Báo Cáo Tổng Hợp Codebase — Agentic Data Engineering

> **Mục đích:** File context toàn diện cho AI (Claude, GPT, v.v.) phân tích sâu repository HCMUS Capstone Project.  
> **Ngày tạo:** 2026-05-24  
> **Repo:** `HCMUS-Capstone-Project` — Multi-Agent ETL/Data Engineering với Human-In-The-Loop  
> **Package Python:** `app/` (không phải `src/` — thư mục `src/` chỉ còn `__pycache__` legacy)

---

## 1. Tóm Tắt Executive

Hệ thống **Agentic Data Engineering** là đồ án tốt nghiệp HCMUS xây dựng pipeline ETL tự động làm sạch dữ liệu dạng bảng (CSV, Excel, JSON) bằng kiến trúc **Multi-Agent** trên **LangGraph**, kế thừa và mở rộng ý tưởng từ bài báo nghiên cứu **AutoDCWorkflow** (Li et al., 2024).

**Điểm khác biệt cốt lõi so với AutoDCWorkflow:**

- Multi-agent song song thay vì single-agent tuần tự
- Human-In-The-Loop (2 checkpoint) thay vì fully automated
- Pandas code generation thay vì OpenRefine operations
- Hỗ trợ concurrent requests + PostgreSQL checkpointing
- Deduplication sequential trước parallel workers

**Luồng pipeline bắt buộc (không được phá vỡ thứ tự):**

```
ingest → profile → select_columns → plan → [HITL-1] → deduplicate
→ parallel_workers → merge → validate → [HITL-2 nếu cần] → report
```

---

## 2. Bối Cảnh Nghiên Cứu

### 2.1 AutoDCWorkflow — Những gì đã adopt

| Insight                              | Implementation trong repo                                                  |
| ------------------------------------ | -------------------------------------------------------------------------- |
| 4-dimension quality model            | `ColumnQualityDimensions` — Accuracy, Relevance, Completeness, Conciseness |
| Select target columns trước planning | `ColumnSelectorAgent` node (`node_select_columns`)                         |
| Quality context cho Planner          | `DataProfiler.profile_async()` enrich `ColumnProfile` với LLM assessment   |

### 2.2 AutoDCWorkflow — Những gì đã từ chối / cải tiến

| Vấn đề AutoDC                  | Giải pháp của repo                                             |
| ------------------------------ | -------------------------------------------------------------- |
| Single-agent, column-by-column | Multi-agent parallel với batching                              |
| Không có HITL                  | 2 checkpoints: plan approval + result approval                 |
| Không xử lý dedup              | `DuplicateHandlerAgent` chạy sequential đầu tiên               |
| 6 OpenRefine ops cứng          | Pandas code generation linh hoạt                               |
| Không concurrent               | `asyncio.gather` + `PipelineManager` + PostgreSQL checkpointer |

### 2.3 Tài liệu tham khảo trong repo

| File                                  | Nội dung                                                 |
| ------------------------------------- | -------------------------------------------------------- |
| `docs/ARCHITECTURE.md`                | Kiến trúc v2, Mermaid diagrams, agent roles              |
| `docs/full_data_flow.md`              | End-to-end data/control flow                             |
| `docs/TEAM_ASSIGNMENT.md`             | Phân công 6 thành viên                                   |
| `docs/REDESIGN_PLAN.md`               | Kế hoạch redesign (hallucination, KB, evaluation)        |
| `docs/HITL/HITL_research.md`          | Nghiên cứu HITL synthesis                                |
| `docs/PHASE1-5_COMPLETION_SUMMARY.md` | Tiến độ các phase triển khai: KB, multi-file, evaluation |

---

## 3. Tech Stack

| Layer                   | Technology                           | Version/Notes                |
| ----------------------- | ------------------------------------ | ---------------------------- |
| **Language**            | Python                               | >=3.13 (pyproject.toml)      |
| **Agent Orchestration** | LangGraph                            | >=1.1.0                      |
| **LLM Framework**       | LangChain                            | >=1.2.0                      |
| **LLM Providers**       | OpenAI GPT-4o/mini, Anthropic Claude | Configurable per agent       |
| **Data Processing**     | pandas, polars, pyarrow              | Parquet canonical format     |
| **SQL Engine**          | DuckDB                               | Per-run file-based DB        |
| **API**                 | FastAPI + WebSocket                  | Port 8000                    |
| **State Persistence**   | PostgreSQL                           | LangGraph AsyncPostgresSaver |
| **Session Cache**       | Redis                                | TTL 24h, run metadata        |
| **Vector Store**        | ChromaDB                             | Knowledge Base RAG           |
| **Embeddings**          | OpenAI text-embedding-3-small        | Via langchain-chroma         |
| **Frontend**            | React 19 + Vite 8 + TypeScript       | Tailwind 4, TanStack Query   |
| **Observability**       | LangSmith, structlog                 | Optional tracing             |
| **Containerization**    | Docker Compose                       | Postgres 16 + Redis 7        |
| **CLI**                 | Typer                                | Entry point `ade`            |

---

## 4. Cấu Trúc Thư Mục Chi Tiết

```
HCMUS-Capstone-Project/
├── app/                          # ← BACKEND CHÍNH (Python package)
│   ├── __init__.py
│   ├── cli.py                    # Typer CLI: `ade serve`, `ade version`
│   │
│   ├── core/                     # Domain models, config, state, exceptions
│   │   ├── config.py             # Pydantic Settings từ .env
│   │   ├── state.py              # PipelineState TypedDict (LangGraph)
│   │   ├── exceptions.py         # ADEBaseError hierarchy
│   │   ├── pipeline_manager.py   # Async queue concurrent pipelines
│   │   ├── format_converter.py   # Multi-format read/write
│   │   ├── model_config.py       # MODEL_REGISTRY, AGENT_MODEL_ASSIGNMENT
│   │   ├── cost_tracker.py       # Token usage/cost logging
│   │   └── model/                # Pydantic domain models
│   │       ├── enums.py          # InputFormat, AgentRole, PipelineStatus, HITLDecision
│   │       ├── quality.py        # QualityDimension, ColumnQualityDimensions
│   │       ├── profile.py        # ColumnProfile, DataProfile, CrossColumnIssue
│   │       ├── selection.py      # TargetColumnSelection
│   │       ├── plan.py           # WorkerTask, ExecutionPlan
│   │       ├── validation.py     # ValidationIssue, ValidationResult
│   │       └── pipeline.py       # UserRequirements, HITLCheckpoint, PipelineRun
│   │
│   ├── graph/                    # LangGraph pipeline definition
│   │   ├── pipeline.py           # build_graph() — StateGraph wiring
│   │   ├── nodes.py              # 11 async node implementations
│   │   └── edges.py              # after_validate() conditional routing
│   │
│   ├── agents/                   # Multi-agent implementations
│   │   ├── base.py               # BaseAgent — LLM, ReAct tool loop
│   │   ├── column_selector/      # ColumnSelectorAgent + prompts
│   │   ├── planner/              # PlannerAgent + RAG KnowledgeBase + prompts
│   │   ├── duplicate_handler/    # DuplicateHandlerAgent (sequential)
│   │   ├── null_type_handler/    # NullTypeHandlerAgent (parallel, code gen)
│   │   ├── validator_agent/      # ValidatorAgent (4-layer) + unauthorized_change_detector
│   │   └── reporter/             # ReporterAgent (export + JSON report)
│   │
│   ├── ingestion/                # File parsing & normalization
│   │   ├── normalizer.py         # detect_format → parse → Parquet canonical
│   │   ├── parsers/              # CSV, Excel, JSON parsers
│   │   └── duckdb/duckdb_mapper.py  # Per-run DuckDB: raw/canonical tables
│   │
│   ├── tools/                    # Non-agent utilities
│   │   ├── data_profiler/        # DataProfiler (3-phase), StatisticalProfiler
│   │   ├── column_inspector/     # ColumnQualityInspector, CrossColumnInspector
│   │   └── sql_executer/         # SQLExecutor (DuckDB wrapper)
│   │
│   ├── memory/                   # Persistence & RAG
│   │   ├── knowledge_base.py     # Chroma RAG: best_practices, chat_history, past_tasks
│   │   ├── vector_store.py       # Chroma + OpenAI embeddings
│   │   ├── session_store.py      # Redis async session metadata
│   │   ├── chat_history.py       # Conversation persistence
│   │   ├── best_practices.json   # 36 curated cleaning rules (v2.0)
│   │   └── .kb_store/            # Persisted Chroma SQLite
│   │
│   ├── hitl/                     # Human-In-The-Loop service
│   │   └── service.py            # submit_decision, get_pending_checkpoint
│   │
│   ├── api/                      # FastAPI application
│   │   ├── main.py               # App factory, lifespan, checkpointer, CORS
│   │   ├── websocket.py          # /ws/{run_id} realtime events
│   │   └── routes/
│   │       ├── upload.py         # POST upload, POST /multi, GET profile
│   │       ├── pipeline.py       # GET status, GET state
│   │       ├── hitl.py           # GET checkpoint, POST decision
│   │       └── reports.py        # GET report, GET download
│   │
│   ├── evaluation/               # Thesis evaluation metrics
│   │   ├── metrics.py            # Hallucination, RequirementAdherence, DataFidelity
│   │   └── comparator.py         # DataComparator input vs output
│   │
│   └── services/                 # LEGACY — duplicate validator copy
│       └── agents/validator_agent/agent.py
│
├── frontend/                     # React SPA
│   ├── src/
│   │   ├── App.tsx               # Step router: upload|profile|pipeline|result
│   │   ├── api/                  # axios client + pipelineApi services
│   │   ├── lib/                  # pipelineSession URL sync, utils
│   │   └── components/
│   │       ├── layout/Header.tsx
│   │       └── views/
│   │           ├── UploadView.tsx
│   │           ├── PipelineView.tsx
│   │           ├── PipelineHitlPanel.tsx
│   │           └── ResultView.tsx
│   └── package.json              # React 19, Vite 8, Tailwind 4
│
├── tests/
│   ├── conftest.py               # Fixtures: sample_csv, sample_excel, clean_df
│   ├── test_pipeline_manager.py
│   ├── test_format_converter.py
│   ├── test_upload_multi.py
│   ├── test_knowledge_base.py
│   ├── test_practices_structure.py
│   ├── benchmarks/test_pipeline_throughput.py
│   └── evaluation/test_cases/    # CSV fixtures: casing, null, semantic drift
│
├── scripts/
│   ├── simulate_load.py          # HTTP load test N concurrent uploads
│   └── merge_best_practices.py   # Merge research practices into KB JSON
│
├── docs/                         # Documentation (xem §2.3)
├── docker-compose.yml            # postgres + redis; profile `full` = API
├── Dockerfile                    # Python 3.11-slim (NOTE: pyproject requires 3.13)
├── Makefile / make.ps1           # Dev automation
├── pyproject.toml                # Dependencies, CLI, ruff, mypy, pytest
└── .env.example                  # Environment template
```

---

## 5. Kiến Trúc Pipeline LangGraph

### 5.1 Sơ đồ luồng

```mermaid
flowchart TB
    START --> ingest
    ingest --> profile
    profile --> select_columns
    select_columns --> plan
    plan --> hitl_plan

    hitl_plan -->|approve| deduplicate
    hitl_plan -->|modify| plan
    hitl_plan -->|reject| END

    deduplicate --> parallel_workers
    parallel_workers --> merge
    merge --> validate

    validate -->|passed| report
    validate -->|retry, count<=2| parallel_workers
    validate -->|needs_human_review| hitl_result

    hitl_result -->|approve/reject| report
    hitl_result -->|modify| plan

    report --> END
```

### 5.2 Chi tiết từng node

| #   | Node               | File       | Chức năng                                                    | Agent/Tool                                      |
| --- | ------------------ | ---------- | ------------------------------------------------------------ | ----------------------------------------------- |
| 1   | `ingest`           | `nodes.py` | Parse file → canonical Parquet, init DuckDB                  | `ingest_to_canonical()`, `duckdb_mapper`        |
| 2   | `profile`          | `nodes.py` | 3-phase profiling (statistical + LLM quality + cross-column) | `DataProfiler.profile_async()`                  |
| 3   | `select_columns`   | `nodes.py` | Lọc target vs skipped columns                                | `ColumnSelectorAgent`                           |
| 4   | `plan`             | `nodes.py` | Tạo ExecutionPlan với RAG                                    | `PlannerAgent` + `KnowledgeBase`                |
| 5   | `hitl_plan`        | `nodes.py` | **HITL-1:** interrupt() plan approval                        | LangGraph `interrupt()`                         |
| 6   | `deduplicate`      | `nodes.py` | Xử lý duplicate **sequential** (trước parallel)              | `DuplicateHandlerAgent`                         |
| 7   | `parallel_workers` | `nodes.py` | Fan-out null/type cleaning theo batches                      | `NullTypeHandlerAgent` × N via `asyncio.gather` |
| 8   | `merge`            | `nodes.py` | Gộp partial Parquets, carry skipped columns                  | Pure Python/pandas                              |
| 9   | `validate`         | `nodes.py` | 4-layer validation gate                                      | `ValidatorAgent`                                |
| 10  | `hitl_result`      | `nodes.py` | **HITL-2:** interrupt() result approval (conditional)        | LangGraph `interrupt()`                         |
| 11  | `report`           | `nodes.py` | Export cleaned file + JSON report                            | `ReporterAgent`                                 |

### 5.3 Conditional routing sau validate

File: `app/graph/edges.py` — function `after_validate(state)`:

| Điều kiện                                                  | Route tới                  |
| ---------------------------------------------------------- | -------------------------- |
| `validation_result.needs_human_review == True`             | `hitl_result`              |
| `validation_result.passed == False` AND `retry_count <= 2` | `parallel_workers` (retry) |
| Else                                                       | `report`                   |

### 5.4 Graph builder

File: `app/graph/pipeline.py` — `build_graph() -> StateGraph`

Compiled trong `app/api/main.py` với:

- `AsyncPostgresSaver.from_conn_string(settings.postgres_url)`
- `thread_id = run_id` cho mỗi pipeline execution

---

## 6. PipelineState — Single Source of Truth

File: `app/core/state.py`

**Thiết kế quan trọng:**

- Extends `MessagesState` (LangGraph native)
- **DataFrame KHÔNG lưu trong state** — chỉ file path (`canonical_path`, `processed_path`)
- Lists dùng `Annotated[..., operator.add]` reducer cho parallel node append
- Tất cả fields Optional trừ identity fields

### 6.1 Các nhóm field chính

```python
class PipelineState(MessagesState):
    # Identity
    run_id: str
    session_id: str
    status: PipelineStatus          # QUEUED | RUNNING | AWAITING_HITL | COMPLETED | FAILED

    # Ingestion
    input_format: InputFormat       # CSV | EXCEL | JSON | PARQUET
    input_path: str                 # Raw uploaded file
    canonical_path: str             # Normalized Parquet
    mapping_metadata: dict | None   # Schema provenance
    output_format: InputFormat
    output_path: str | None

    # User intent
    user_requirements: UserRequirements | None  # Free-text cleaning requirements

    # Profiling
    data_profile: DataProfile | None

    # Column selection (AutoDC §4.1)
    column_selection: TargetColumnSelection | None

    # Planning
    execution_plan: ExecutionPlan | None

    # HITL
    hitl_checkpoints: Annotated[list[HITLCheckpoint], operator.add]
    awaiting_hitl: bool
    hitl_last_decision: str | None  # approve | reject | modify
    hitl_user_feedback: str | None
    modify_count: int               # Max 3 re-plan cycles

    # Workers
    worker_results: Annotated[list[dict], operator.add]
    completed_task_ids: Annotated[list[str], operator.add]
    processed_path: str | None

    # Validation
    validation_result: ValidationResult | None
    retry_count: int                # Max 2 retry cycles

    # Reporting
    report_path: str | None

    # Observability
    agent_logs: Annotated[list[dict], operator.add]
    total_tokens_used: int
    error_message: str | None
```

### 6.2 Factory function

`initial_state(run_id, session_id, input_format, input_filename, input_path, user_requirements)` — khởi tạo state mặc định cho pipeline mới.

---

## 7. Domain Models (Pydantic)

Tất cả models trong `app/core/model/`, re-export qua `models.py`.

### 7.1 Enums (`enums.py`)

| Enum             | Values                                                                                 |
| ---------------- | -------------------------------------------------------------------------------------- |
| `InputFormat`    | CSV, TSV, EXCEL, JSON, JSONL, PARQUET                                                  |
| `PipelineStatus` | QUEUED, RUNNING, AWAITING_HITL, COMPLETED, FAILED, CANCELLED                           |
| `AgentRole`      | PLANNER, COLUMN_SELECTOR, DUPLICATE_HANDLER, NULL_TYPE_HANDLER, VALIDATOR, REPORTER    |
| `HITLDecision`   | APPROVE, REJECT, MODIFY                                                                |
| `ErrorType`      | NULL_VIOLATION, TYPE_MISMATCH, DUPLICATE, QUALITY_REGRESSION, UNAUTHORIZED_CHANGE, ... |

### 7.2 Quality Model (`quality.py`)

```python
class ColumnQualityDimensions:
    accuracy: QualityDimension      # Free from errors, wrong types
    relevance: QualityDimension     # Relevant to user requirements
    completeness: QualityDimension  # Sufficient non-null values
    conciseness: QualityDimension   # Standardised, no duplicate representations

    def failing_dimensions(self) -> list[str]  # Returns dims with score < threshold
```

**Chạy 2 lần:** profiling phase (before) + validation phase (after) → so sánh delta.

### 7.3 Execution Plan (`plan.py`)

```python
class WorkerTask:
    task_id: str
    task_type: str                  # "deduplicate" | "null_type"
    target_columns: list[str]
    instructions: dict[str, Any]    # JSON structured — KHÔNG phải natural language
    priority: int

class ExecutionPlan:
    plan_id: str
    sequential_tasks: list[WorkerTask]   # Dedup MUST be first
    parallel_task_groups: list[list[WorkerTask]]  # Batched null/type tasks
    rationale: str
    estimated_token_cost: int | None
```

### 7.4 Validation Result (`validation.py`)

```python
class ValidationResult:
    passed: bool
    needs_human_review: bool        # Triggers HITL-2
    issues: list[ValidationIssue]
    quality_delta: dict[str, float] # Before vs after per dimension
    layer_results: dict[str, bool]  # layer_1_statistical, layer_2_constraints, ...
```

---

## 8. Agents — Chi Tiết Từng Agent

Tất cả agents kế thừa `BaseAgent` (`app/agents/base.py`):

- `_build_llm()` — construct LLM theo `AgentRole` từ `model_config.py`
- `_run_tool_loop()` — ReAct pattern với LangChain tools
- `run(state)` — abstract method, mỗi agent implement

### 8.1 Model Assignment

File: `app/core/model_config.py`

| Agent                   | Model Key       | Provider  | Rationale                            |
| ----------------------- | --------------- | --------- | ------------------------------------ |
| `PlannerAgent`          | claude-sonnet-4 | Anthropic | Complex reasoning, structured output |
| `ColumnSelectorAgent`   | gpt-4o-mini     | OpenAI    | Simple filtering                     |
| `DuplicateHandlerAgent` | gpt-4o-mini     | OpenAI    | Rule-based (minimal LLM)             |
| `NullTypeHandlerAgent`  | gpt-4o-mini     | OpenAI    | Code generation + self-correction    |
| `ValidatorAgent`        | claude-sonnet-4 | Anthropic | Quality inspection                   |
| `ReporterAgent`         | gpt-4o-mini     | OpenAI    | Template-based output                |

### 8.2 ColumnSelectorAgent

- **File:** `app/agents/column_selector/agent.py`
- **Prompts:** `app/agents/column_selector/prompts.py`
- **Input:** Full `DataProfile` + `UserRequirements`
- **Output:** `TargetColumnSelection` (target_columns, skipped_columns, rationale)
- **Vị trí pipeline:** Sau profile, trước plan
- **Mục đích:** Giảm token context cho Planner, tránh touch irrelevant columns

### 8.3 PlannerAgent

- **File:** `app/agents/planner/agent.py`
- **Prompts:** `app/agents/planner/prompts.py` — `PLAN_SYSTEM`, `PLAN_PROMPT`
- **RAG:** Khởi tạo `KnowledgeBase()`, gọi `get_relevant_practices()` + `get_similar_tasks()`
- **Input:** `DataProfile` (target cols only) + quality dimensions + user requirements
- **Output:** `ExecutionPlan` với sequential_tasks (dedup first) + parallel_task_groups
- **Re-plan:** Hỗ trợ modify từ HITL với `hitl_user_feedback`

### 8.4 DuplicateHandlerAgent

- **File:** `app/agents/duplicate_handler/agent.py`
- **Strategies:** `keep_first`, `keep_last`, `drop_all`, `subset` (specific columns)
- **Bắt buộc sequential:** Chạy trước parallel workers vì dedup thay đổi row count → index misalignment
- **Output:** Ghi lại canonical Parquet

### 8.5 NullTypeHandlerAgent

- **File:** `app/agents/null_type_handler/agent.py`
- **Prompts:** `app/agents/null_type_handler/prompts.py` — pandas code generation rules
- **Pattern:** LLM generate pandas code → execute → self-correction on error
- **Tools:** `inspect_column_values` (LangChain tool)
- **Parallel:** Mỗi instance xử lý 1 batch columns (max `settings.max_columns_per_worker = 20`)
- **Output:** Partial Parquet files → merge node gộp lại
- **Data fidelity rules trong prompt:** Không đổi casing, không fill unauthorized, không truncate

### 8.6 ValidatorAgent

- **File:** `app/agents/validator_agent/agent.py`
- **Supporting:** `unauthorized_change_detector.py`

**4-layer validation:**

| Layer | Check                 | Method                                                         |
| ----- | --------------------- | -------------------------------------------------------------- |
| 1     | Statistical           | Null counts, duplicate counts vs pre-profile                   |
| 2     | User constraints      | Type checks theo requirements                                  |
| 3     | Quality re-inspection | 4-dimension LLM re-assess target columns, compare before/after |
| 4     | Unauthorized changes  | Casing, semantic drift, unauthorized fills, truncation         |

**Routing logic:**

- `passed=True` → report
- `passed=False`, `retry_count <= 2` → parallel_workers (retry)
- Persistent errors after max retries → `needs_human_review=True` → HITL-2

### 8.7 ReporterAgent

- **File:** `app/agents/reporter/agent.py`
- **Actions:**
  1. Export cleaned data qua `export_from_canonical()` (same format as input)
  2. Write `processing_report.json` (quality delta, operations log, token cost)
  3. Set `status = COMPLETED`

---

## 9. Tools (Non-Agent Utilities)

### 9.1 DataProfiler

- **File:** `app/tools/data_profiler/data_profiler.py`
- **3 phases:**
  1. **Statistical** (sync): null rate, unique ratio, dtype, patterns — `StatisticalProfiler`
  2. **LLM Quality** (async): 4-dimension per column — `ColumnQualityInspector`
  3. **Cross-column** (async): temporal ordering, functional deps — `CrossColumnInspector`
- **Methods:** `profile()`, `profile_async()`

### 9.2 ColumnQualityInspector

- **File:** `app/tools/column_inspector/column_quality_inspector.py`
- **Output:** JSON structured `ColumnQualityDimensions`
- **Prompts inline:** `SYSTEM_PROMPT`, `INSPECT_PROMPT`
- **Reused by:** Profiler (before) + Validator (after)

### 9.3 StatisticalProfiler

- **File:** `app/tools/data_profiler/statistical_profiler.py`
- **Standalone EDA:** ColumnStat dataclass, PK/categorical heuristics
- **CLI entry point** available

### 9.4 SQLExecutor

- **File:** `app/tools/sql_executer/sql_executor.py`
- **DuckDB in-memory SQL** on Parquet files

---

## 10. Ingestion Pipeline

### 10.1 Supported formats

| Format             | Parser            | Notes                                           |
| ------------------ | ----------------- | ----------------------------------------------- |
| CSV/TSV/TXT        | `csv_parser.py`   | chardet encoding, delimiter sniffing, dtype=str |
| Excel (.xlsx/.xls) | `excel_parser.py` | First sheet only                                |
| JSON/JSONL/NDJSON  | `json_parser.py`  | One-level flatten via json_normalize            |

### 10.2 Canonical format

**Parquet** là internal canonical format. Flow:

```
Raw file → Parser → DataFrame → Parquet (canonical_path)
                                    ↓
                            All agents read/write Parquet
                                    ↓
                            Export → same format as input
```

### 10.3 DuckDB Mapper

- **File:** `app/ingestion/duckdb/duckdb_mapper.py`
- Per-run file-based DuckDB database
- Tables: raw, canonical, default `data` view
- Column mapping metadata for SQL lineage

---

## 11. Human-In-The-Loop (HITL)

### 11.1 Kiến trúc

- **Mechanism:** LangGraph `interrupt()` inside graph nodes
- **Persistence:** PostgreSQL checkpointer (graph state frozen at interrupt)
- **Resume:** `Command(resume={"decision": ..., "feedback": ...})`
- **Service:** `app/hitl/service.py`

### 11.2 HITL-1: Plan Approval

| Property  | Value                                                      |
| --------- | ---------------------------------------------------------- |
| Node      | `node_hitl_plan`                                           |
| Trigger   | Always — sau plan, trước workers                           |
| Payload   | execution_plan, column_selection, modify limits            |
| Decisions | approve → deduplicate, modify → plan (max 3), reject → END |

### 11.3 HITL-2: Result Approval

| Property  | Value                                          |
| --------- | ---------------------------------------------- |
| Node      | `node_hitl_result`                             |
| Trigger   | Conditional — khi `needs_human_review=True`    |
| Payload   | validation_result, persistent quality issues   |
| Decisions | approve/reject → report, modify → plan (max 3) |

### 11.4 API Flow

```
Frontend polls GET /api/v1/pipeline/{run_id}/status
  OR listens WebSocket /ws/{run_id}
    → detects interrupt in snap.tasks[].interrupts

User submits POST /api/v1/hitl/{run_id}/decision
  → HITLService.submit_decision()
  → Background: pipeline.astream(Command(resume=...))
  → Graph continues from interrupt point
```

---

## 12. Knowledge Base & RAG

### 12.1 Architecture

- **File:** `app/memory/knowledge_base.py`
- **Vector store:** ChromaDB persisted at `app/memory/.kb_store/`
- **Embeddings:** OpenAI `text-embedding-3-small`

### 12.2 Collections

| Collection       | Purpose                   | Methods                                                      |
| ---------------- | ------------------------- | ------------------------------------------------------------ |
| `best_practices` | 36 curated cleaning rules | `get_relevant_practices()`, `get_practices_by_category()`    |
| `chat_history`   | Conversation persistence  | Chat history methods                                         |
| `past_tasks`     | Similar task retrieval    | `get_similar_tasks()`, `record_successful/failed_strategy()` |

### 12.3 Best Practices Data

- **File:** `app/memory/best_practices.json`
- **Version:** 2.0 (updated 2026-05-10)
- **Count:** 36 practices
- **Categories:** null_handling, data_fidelity, type_casting, deduplication, formatting, ...

### 12.4 Integration

`PlannerAgent` khởi tạo `KnowledgeBase()` và inject relevant practices vào planning prompt.

---

## 13. API Endpoints

Base URL: `http://localhost:8000`

### 13.1 Upload

| Method | Path                              | Description                       |
| ------ | --------------------------------- | --------------------------------- |
| POST   | `/api/v1/upload/`                 | Single file upload + requirements |
| POST   | `/api/v1/upload/multi`            | Multi-file upload                 |
| GET    | `/api/v1/upload/{run_id}/profile` | Get profiling results             |

### 13.2 Pipeline

| Method | Path                               | Description                  |
| ------ | ---------------------------------- | ---------------------------- |
| GET    | `/api/v1/pipeline/{run_id}/status` | Run status + HITL detection  |
| GET    | `/api/v1/pipeline/{run_id}/state`  | Full pipeline state snapshot |

### 13.3 HITL

| Method | Path                               | Description                  |
| ------ | ---------------------------------- | ---------------------------- |
| GET    | `/api/v1/hitl/{run_id}/checkpoint` | Pending checkpoint payload   |
| POST   | `/api/v1/hitl/{run_id}/decision`   | Submit approve/reject/modify |

### 13.4 Reports

| Method | Path                                | Description            |
| ------ | ----------------------------------- | ---------------------- |
| GET    | `/api/v1/reports/{run_id}/report`   | JSON processing report |
| GET    | `/api/v1/reports/{run_id}/download` | Download cleaned file  |

### 13.5 WebSocket

| Path           | Events                                                   |
| -------------- | -------------------------------------------------------- |
| `/ws/{run_id}` | `status_change`, `hitl_checkpoint`, `completed`, `error` |

### 13.6 Health

| Method | Path      | Description   |
| ------ | --------- | ------------- |
| GET    | `/`       | API info JSON |
| GET    | `/health` | Health check  |
| GET    | `/docs`   | Swagger UI    |

---

## 14. Frontend

### 14.1 Stack

- React 19, Vite 8, TypeScript
- Tailwind CSS 4
- TanStack Query (data fetching)
- Axios (HTTP client)

### 14.2 Application Flow

```
App.tsx step router:
  upload → profile → pipeline → result

URL sync via pipelineSession.ts:
  ?step=upload|profile|pipeline|result&run={run_id}
```

### 14.3 Views

| View              | File                    | Purpose                           |
| ----------------- | ----------------------- | --------------------------------- |
| UploadView        | `UploadView.tsx`        | File upload + requirements form   |
| PipelineView      | `PipelineView.tsx`      | Live status via polling/WebSocket |
| PipelineHitlPanel | `PipelineHitlPanel.tsx` | HITL approve/reject/modify UI     |
| ResultView        | `ResultView.tsx`        | Final report + download           |

### 14.4 API Client

- **Base:** `frontend/src/api/client.ts` — axios to `localhost:8000/api/v1`
- **Services:** `frontend/src/api/services.ts` — `pipelineApi` wrapper

---

## 15. Infrastructure & Deployment

### 15.1 Docker Compose

```yaml
services:
  postgres: # postgres:16-alpine, port 5432, db=ade_db
  redis: # redis:7-alpine, port 6379
  api: # profile: full, port 8000, depends on postgres+redis
```

### 15.2 Environment Variables

File: `.env.example`

| Variable                   | Default                                            | Purpose                          |
| -------------------------- | -------------------------------------------------- | -------------------------------- |
| `OPENAI_API_KEY`           | —                                                  | OpenAI LLM                       |
| `ANTHROPIC_API_KEY`        | —                                                  | Anthropic LLM                    |
| `POSTGRES_URL`             | `postgresql://user:password@localhost:5432/ade_db` | LangGraph checkpointer           |
| `REDIS_URL`                | `redis://localhost:6379/0`                         | Session store                    |
| `MAX_CONCURRENT_PIPELINES` | 10                                                 | PipelineManager queue limit      |
| `WORKER_CONCURRENCY`       | 4                                                  | Parallel worker batches          |
| `HITL_TIMEOUT_SECONDS`     | 300                                                | HITL wait timeout                |
| `MAX_COLUMNS_PER_WORKER`   | 20                                                 | Batch size for null/type workers |

### 15.3 Dev Setup

```bash
make setup    # venv + pip + .env + docker compose
make run      # ade serve (uses .venv/bin/ade)
make test     # pytest
```

**Quan trọng:** Luôn dùng `.venv` Python, không dùng Anaconda base (NumPy version conflicts).

---

## 16. Testing & Evaluation

### 16.1 Unit/Integration Tests

| File                          | Coverage                              |
| ----------------------------- | ------------------------------------- |
| `test_pipeline_manager.py`    | Concurrency queue, status transitions |
| `test_format_converter.py`    | CSV/Excel/JSON/Parquet conversion     |
| `test_upload_multi.py`        | FastAPI multi-file upload             |
| `test_knowledge_base.py`      | KB RAG smoke test                     |
| `test_practices_structure.py` | Validate 36 best practices JSON       |

### 16.2 Benchmarks

| File                                           | Purpose                                  |
| ---------------------------------------------- | ---------------------------------------- |
| `tests/benchmarks/test_pipeline_throughput.py` | Parametrized concurrency [1,5,10]        |
| `scripts/simulate_load.py`                     | HTTP load test `--concurrent N --rows M` |

### 16.3 Evaluation Metrics (Thesis)

File: `app/evaluation/metrics.py`

| Metric                        | Description                           |
| ----------------------------- | ------------------------------------- |
| `HallucinationMetrics`        | Detect unauthorized data changes      |
| `RequirementAdherenceMetrics` | Did cleaning match user requirements? |
| `DataFidelityMetrics`         | Input vs output fidelity score        |

Fixtures: `tests/evaluation/test_cases/` — casing, null, semantic drift scenarios.

---

## 17. Phân Công Team (6 thành viên)

| Thành viên     | Module chính                                                                  | Priority |
| -------------- | ----------------------------------------------------------------------------- | -------- |
| **Trần Vĩ**    | `app/core/`, `app/graph/`, `app/api/`, Docker, benchmarks                     | P0       |
| **Quân Lý**    | `app/ingestion/`, `app/tools/`, `app/memory/knowledge_base.py`                | P0       |
| **Quân Bùi**   | `app/agents/planner/`, `app/agents/column_selector/`, prompts                 | P0       |
| **Thiện Nhân** | `app/agents/null_type_handler/`, parallel batching, retry                     | P1       |
| **Thiên Đức**  | `app/agents/validator_agent/`, `duplicate_handler/`, `reporter/`, `app/hitl/` | P1       |
| **Quân Huỳnh** | `frontend/` 100% — UI, WebSocket, HITL panel                                  | P2-P3    |

**Lưu ý ranh giới:** Mỗi agent/node tuân thủ interface contracts (`BaseAgent`, `PipelineState`, JSON structured outputs). Không sửa module người khác mà không kiểm tra dependencies.

---

## 18. Technical Debt & Known Issues

| Issue                                    | Location                                            | Notes                                                          |
| ---------------------------------------- | --------------------------------------------------- | -------------------------------------------------------------- |
| Legacy `src/` path in docs               | `TEAM_ASSIGNMENT.md`, `ARCHITECTURE.md` §7          | Docs reference `src/` but code is in `app/`                    |
| Dockerfile Python 3.11 vs pyproject 3.13 | `Dockerfile`                                        | Version mismatch                                               |
| Legacy validator duplicate               | `app/services/agents/validator_agent/`              | Unused copy, pipeline uses `app/agents/validator_agent/`       |
| Missing test files                       | `tests/test_statistical_profiler.py`, `tests/unit/` | Referenced in docs/Makefile but not present                    |
| Empty fixtures dir                       | `tests/fixtures/`                                   | conftest references FIXTURE_DIR but empty                      |
| Makefile stale refs                      | `Makefile`                                          | References `src.api.main`, `tests/unit/`                       |
| Model config vs settings mismatch        | `model_config.py` vs `config.py`                    | model_config assigns claude-sonnet-4, settings defaults gpt-4o |

---

## 19. Interface Contracts (Quan Trọng Cho AI)

Khi sửa code, **phải tuân thủ** các contracts sau:

### 19.1 Agent Contract

```python
class BaseAgent:
    async def run(self, state: PipelineState, **kwargs) -> dict[str, Any]:
        """Returns partial state update dict."""
```

### 19.2 Structured Outputs (KHÔNG dùng natural language)

```python
# WorkerTask.instructions phải là JSON dict:
{"strategy": "fill_mean", "target_columns": ["age"], "null_replacement": "mean"}

# ExecutionPlan output phải parse được thành Pydantic model
# TargetColumnSelection phải có target_columns + skipped_columns lists
```

### 19.3 State Update Pattern

```python
# Nodes return dict partial updates, KHÔNG mutate state trực tiếp
return {"data_profile": profile, "status": PipelineStatus.RUNNING}
```

### 19.4 HITL Resume Contract

```python
Command(resume={"decision": "approve|reject|modify", "feedback": "optional text"})
```

---

## 20. Prompt Engineering Structure

Prompts nằm trong Python modules (không phải YAML/JSON):

| File                           | Prompts                                          | Pattern                                      |
| ------------------------------ | ------------------------------------------------ | -------------------------------------------- |
| `planner/prompts.py`           | `PLAN_SYSTEM`, `PLAN_PROMPT`                     | Dedup-first rules, data fidelity constraints |
| `column_selector/prompts.py`   | `SELECT_COLUMNS_SYSTEM`, `SELECT_COLUMNS_PROMPT` | Target vs skipped rationale                  |
| `null_type_handler/prompts.py` | `SYSTEM_PROMPT`, `CODE_PROMPT`                   | Pandas code gen, fidelity rules              |
| `column_quality_inspector.py`  | Inline `SYSTEM_PROMPT`, `INSPECT_PROMPT`         | 4-dimension JSON output                      |

**Pattern chung:** System message + human template với `{placeholders}`, output enforced via `response_format={"type": "json_object"}`.

---

## 21. Quick Reference — Key Files Index

| Cần hiểu...       | Đọc file                                                            |
| ----------------- | ------------------------------------------------------------------- |
| Pipeline flow     | `app/graph/pipeline.py`, `app/graph/nodes.py`, `app/graph/edges.py` |
| State schema      | `app/core/state.py`, `app/core/model/*.py`                          |
| Agent logic       | `app/agents/*/agent.py`                                             |
| API endpoints     | `app/api/routes/*.py`, `app/api/main.py`                            |
| HITL mechanism    | `app/hitl/service.py`, `node_hitl_plan/result` in nodes.py          |
| Config/env        | `app/core/config.py`, `.env.example`                                |
| Frontend flow     | `frontend/src/App.tsx`, `frontend/src/api/services.ts`              |
| Architecture docs | `docs/ARCHITECTURE.md`, `docs/full_data_flow.md`                    |
| Team ownership    | `docs/TEAM_ASSIGNMENT.md`                                           |

---

## 22. Hướng Dẫn Sử Dụng File Này Với Claude

Khi paste context cho Claude, có thể kèm prompt mẫu:

```
Bạn đang phân tích repository Agentic Data Engineering (HCMUS Capstone).
Đọc file CODEBASE_CONTEXT_REPORT.md để hiểu:
- Kiến trúc Multi-Agent LangGraph pipeline
- 11 nodes và thứ tự bắt buộc
- 6 agents và interface contracts
- 2 HITL checkpoints
- Team ownership boundaries

Câu hỏi của tôi: [YOUR QUESTION HERE]

Khi đề xuất sửa code:
1. Tuân thủ thứ tự pipeline (§5)
2. Không phá interface contracts (§19)
3. Respect team boundaries (§17)
4. Output phải là JSON structured, không natural language
```

---

## 23. Glossary

| Term                    | Definition                                                          |
| ----------------------- | ------------------------------------------------------------------- |
| **Canonical format**    | Internal Parquet representation after ingestion                     |
| **HITL**                | Human-In-The-Loop — graph interrupt for user approval               |
| **WorkerTask**          | Atomic cleaning task in ExecutionPlan                               |
| **4-dimension quality** | Accuracy, Relevance, Completeness, Conciseness                      |
| **Batch**               | Group of columns processed by one NullTypeHandlerAgent instance     |
| **Checkpointer**        | PostgreSQL persistence for LangGraph state (enables resume)         |
| **RAG**                 | Retrieval-Augmented Generation — KB practices injected into Planner |
| **Self-correction**     | Worker retries code generation on execution error                   |

---

_Tài liệu này được generate tự động từ codebase scan. Cập nhật khi có thay đổi lớn về architecture._
