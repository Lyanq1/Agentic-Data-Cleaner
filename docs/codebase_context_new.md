# Báo Cáo Tổng Hợp Codebase — Agentic Data Engineering

> **Mục đích:** File context toàn diện cho AI (Gemini, Claude, GPT, v.v.) phân tích sâu repository HCMUS Capstone Project.  
> **Ngày cập nhật:** 2026-06-23 (Cập nhật khớp 100% với cấu trúc và code thực tế hiện tại)  
> **Repo:** `Agentic-Data-Cleaner` — Multi-Agent ETL/Data Engineering với Human-In-The-Loop  
> **Package Python:** `app/`

---

## 1. Tóm Tắt Executive

Hệ thống **Agentic Data Engineering** là đồ án tốt nghiệp HCMUS xây dựng pipeline ETL tự động làm sạch dữ liệu dạng bảng (CSV, Excel, JSON) bằng kiến trúc **Multi-Agent** trên **LangGraph**, kết hợp cơ chế kiểm soát chất lượng tự động thông qua **Custom Pandas Validator** và tương tác người dùng **Human-In-The-Loop (HITL)**.

**Luồng pipeline thực tế hiện tại:**
```
[Ingest] (normalizer) 
   ↓
[profiler_node] (Thống kê EDA)
   ↓
[semantic_profile_node] (LLM Semantic Audit & Quality Review)
   ↓
[input_validator_node] (Đánh giá chất lượng & Yêu cầu làm rõ)
   ↓ ── (Nếu status == 'needs_clarification' → HITL: Dừng chờ user trả lời)
[planner_node] (Lập kế hoạch làm sạch ExecutionPlan)
   ↓ ── (HITL: interrupt_before ở các worker task)
[deduplication] ── [validator] (Pandas check & Retry/Replan loop)
   ↓
[null_handling] ── [validator] (Pandas check & Retry/Replan loop)
   ↓
[type_casting]  ── [validator] (Pandas check & Retry/Replan loop)
   ↓ ── (HITL: interrupt_before)
[report_agent] (Tạo báo cáo kết quả và kết thúc)
```

---

## 2. Tech Stack

| Layer                   | Technology                           | Version/Notes                |
| ----------------------- | ------------------------------------ | ---------------------------- |
| **Language**            | Python                               | >=3.13                       |
| **Agent Orchestration** | LangGraph                            | >=1.1.0                      |
| **LLM Framework**       | LangChain                            | >=1.2.0                      |
| **LLM Providers**       | OpenAI (mặc định), Anthropic         | Cấu hình qua `.env`          |
| **Data Processing**     | pandas, pyarrow                      | Parquet format cho Ingestion |
| **Validation Engine**   | Custom Pandas Validator              | Thực thi validation rules trong quality_control |
| **Database**            | PostgreSQL                           | Lưu trữ Lineage và dữ liệu   |
| **ORM & Driver**        | SQLAlchemy, psycopg                  | Quản lý kết nối PostgreSQL   |
| **Session Cache**       | Redis                                | Quản lý session              |
| **API Framework**       | FastAPI + Uvicorn                    | Port 8000                    |
| **Frontend**            | React + Vite + TypeScript            | Tailwind CSS, TanStack Query |

---

## 3. Cấu Trúc Thư Mục Chi Tiết Thực Tế

```
Agentic-Data-Cleaner/
├── app/                          # ← BACKEND CHÍNH
│   ├── __init__.py
│   ├── main.py                   # Khởi tạo FastAPI app, lifespan, CORS, và app-level WebSocket (/ws/{run_id})
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── dependencies.py
│   │   ├── middleware.py         # Đăng ký CORS, logging middleware
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── deduplication.py  # Debug endpoint chạy trực tiếp deduplication agent (/dedup/run)
│   │       ├── health.py         # Liveness (/health) & Readiness (/readiness)
│   │       ├── pipeline.py       # Endpoints: run, state, download, preview, resolve, approve_plan
│   │       ├── router.py         # Khai báo prefix /api/v1 và gom các routers v1
│   │       └── websocket.py      # WebSocket router /ws/{run_id} cho log streaming
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   └── config.py             # Pydantic BaseSettings, load biến môi trường từ .env
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── callbacks.py          # TokenTrackerCallback quản lý đếm token sử dụng của LLM
│   │   ├── database.py           # Thiết lập SQLAlchemy engine, SessionLocal, init_db()
│   │   ├── llm_factory.py        # create_llm() chat model ChatOpenAI / ChatAnthropic với callbacks
│   │   ├── redis_client.py       # Quản lý kết nối Redis
│   │   └── websocket_manager.py  # ConnectionManager phát sóng (broadcast) log tới WS khách
│   │
│   ├── exceptions/
│   │   ├── __init__.py
│   │   └── ingestion_exceptions.py  # IngestionError class
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   └── lineage.py            # SQLAlchemy models: Session, LineageVersion, DatasetRecord (JSONB)
│   │
│   ├── graphs/                   # LangGraph pipeline definition
│   │   ├── __init__.py
│   │   ├── graph.py              # build_graph() — Định nghĩa graph, nodes, conditional edges và checkpointer
│   │   ├── nodes.py              # Implementations của các node trong graph (profiler, validator, v.v.)
│   │   ├── edges.py              # Logic định tuyến phụ trợ
│   │   ├── checkpointer.py       # AsyncPostgresSaver checkpointer cho LangGraph
│   │   └── states/               # Tách biệt các Pydantic state model theo từng domain
│   │       ├── global_state.py   # GlobalState TypedDict (LangGraph) + append_list/merge_agent_logs/sum_metrics helpers
│   │       ├── input_validation.py  # InputValidationResult, ClarificationIssues, NullClarifications, StrategyQuestion, InsightQuestion
│   │       ├── planning.py       # ExecutionPlan, TaskDetail, TaskDetailWrapper
│   │       ├── profiles.py       # SemanticProfile, ColumnSemanticProfileDetail
│   │       ├── profiler_state.py # StatisticalProfile, ColumnStatProfile
│   │       ├── workers.py        # WorkerStates, WorkerStateDetail, DeduplicationResult, DedupDecisionTrace
│   │       └── output_validation.py # ValidationResultItem, TaskVerification, ValidationCheck
│   │
│   ├── agents/                   # Thư mục Multi-agent
│   │   ├── __init__.py
│   │   ├── base.py               # Lớp BaseAgent tích hợp TokenTrackerCallback và LLM binding
│   │   ├── roles.py              # Enum AgentRole (profiler, planner, null_agent, dedup_agent, typecast_agent, v.v.)
│   │   ├── registry.py           # AgentRegistry quản lý đăng ký/khởi tạo Agent tự động
│   │   │
│   │   ├── input_validator/      # Agent kiểm tra input và hỏi clarification
│   │   │   ├── agent.py          # InputValidatorAgent — JSON mode LLM + _apply_allow_missing_overrides
│   │   │   └── prompts.py        # INPUT_VALIDATOR_SYSTEM_PROMPT
│   │   │
│   │   ├── planner/              # Agent lập kế hoạch làm sạch
│   │   │   ├── agent.py
│   │   │   └── prompts.py
│   │   │
│   │   ├── semantic_analyzer/    # Agent profiling ngữ nghĩa & audit chất lượng
│   │   │   ├── profiler_agent.py
│   │   │   └── prompts.py
│   │   │
│   │   ├── deduplication/        # Hybrid deduplication agent (LLM strategy + deterministic exec)
│   │   │   ├── agent.py          # DeduplicationAgent — tool loop + validate + execute + context hashing
│   │   │   ├── models.py         # DedupDecision, ValidatedDedupDecision, DeduplicationAgentInput
│   │   │   └── prompt.py         # build_dedup_messages(), DEDUP_DECISION_JSON_INSTRUCTION
│   │   │
│   │   ├── null_agent/           # Deterministic null handling worker
│   │   │   ├── agent.py          # NullAgent — drop_row / fill_value / fill_mode / fill_mean / fill_median / leave_as_is
│   │   │   └── __init__.py
│   │   │
│   │   ├── type_agent/           # Deterministic type casting worker
│   │   │   ├── agent.py          # TypeCastingAgent — per_column casting + trích xuất định dạng ngày giờ gốc
│   │   │   └── __init__.py
│   │   │
│   │   ├── result_validators/    # Hybrid validator agent (Pandas rules + LLM ReAct)
│   │   │   ├── agent.py          # ValidatorAgent — ReAct loop, gọi perform_data_quality_check
│   │   │   ├── models.py
│   │   │   └── prompts.py
│   │   │
│   │   └── reporter/             # Agent báo cáo tổng kết pipeline
│   │       ├── agent.py
│   │       └── prompts.py
│   │
│   ├── ingestion/                # Ingestion pipeline
│   │   ├── __init__.py
│   │   ├── normalizer.py         # ingest_to_canonical() convert file → Parquet + trả về schema
│   │   └── parsers/              # Parsers cho các loại file
│   │       ├── base.py
│   │       ├── csv_parser.py
│   │       ├── excel_parser.py
│   │       └── json_parser.py
│   │
│   └── tools/                    # Các module chứa tool phụ trợ
│       ├── __init__.py
│       ├── tool_registration.py  # Đăng ký tool cho agents
│       └── data/
│           ├── eda/              # Tool thực hiện EDA thống kê
│           │   ├── __init__.py
│           │   ├── models.py
│           │   ├── profiler.py   # StatisticalProfiler phân tích dữ liệu định dạng bất thường (Dominant Pattern Heuristic)
│           │   ├── tool.py       # perform_eda LangChain tool
│           │   └── utils.py
│           ├── dedup/            # Tool hỗ trợ DeduplicationAgent
│           │   ├── __init__.py
│           │   └── tool.py       # @tool inspect_duplicate_candidates
│           └── quality_control/  # Tool hỗ trợ ValidatorAgent và thực thi kiểm tra Pandas
│               ├── __init__.py
│               ├── models.py     # Định nghĩa ColumnQuality & QualityReport
│               ├── profiler.py   # QualityProfiler phân tích chất lượng dữ liệu sâu
│               ├── tool.py       # perform_data_quality_check
│               └── validator.py  # run_pandas_validation() chạy luật Pandas trên dataframe
│
├── frontend/                     # React App (React + Vite + TypeScript)
├── tests/                        # Hệ thống test (dữ liệu test như hospital-dirty.csv, olist, v.v.)
├── docker-compose.yml            # Khởi tạo Postgres + Redis
└── .env                          # Cấu hình môi trường thực tế
```

---

## 4. Kiến Trúc Pipeline LangGraph & Luồng HITL

### 4.1 Chi tiết các Nodes của Pipeline

Hệ thống định nghĩa 9 nodes chính trong [app/graphs/nodes.py](file:///d:/Agentic-Data-Cleaner/app/graphs/nodes.py):

| Node | Tên hàm | Vai trò | Tương tác Agent/Tool |
| :--- | :--- | :--- | :--- |
| **profiler** | `profiler_node` | Chạy EDA thống kê mô tả trên dataset thô, tạo ra profile kỹ thuật cơ bản. | Gọi `@tool perform_eda` |
| **semantic_profile** | `semantic_profile_node` | Phân tích ngữ nghĩa của từng cột, nhóm logic, tìm mối liên hệ, và audit chất lượng dữ liệu ban đầu. | `SemanticProfilerAgent` |
| **input_validator** | `input_validator_node` | Đối chiếu profile thống kê & ngữ nghĩa với yêu cầu làm sạch của người dùng, xác định có cần làm rõ thông tin hay không. | `InputValidatorAgent` |
| **planner** | `planner_node` | Sinh kế hoạch dọn dẹp dữ liệu chi tiết (`ExecutionPlan`) gồm các task cho deduplication, null handling và type casting. | `PlannerAgent` |
| **deduplication** | `deduplication_node` | Tác nhân con lai (Hybrid Sub-agent) sử dụng LLM để chọn chiến lược dedup (exact_key hoặc exact_full_row) kết hợp thực thi tất định bằng Pandas. | `DeduplicationAgent` |
| **null_handling** | `null_handling_node` | Tác nhân tất định (Deterministic Agent) áp dụng các chiến lược điền/xóa null dựa trên cấu hình từ Planner. | `NullAgent` |
| **type_casting** | `type_casting_node` | Tác nhân tất định (Deterministic Agent) ép kiểu dữ liệu dựa trên Semantic Profile và Planner's work order. | `TypeCastingAgent` |
| **validator** | `validator_node` | Đánh giá kết quả làm sạch bằng phương pháp lai: Gọi Pandas validator chạy trước, sau đó dùng LLM (ReAct) nhận định. Nếu qua test, tự động khôi phục format ngày tháng gốc và ghi vào Lineage Database. | `ValidatorAgent` |
| **report_agent** | `report_agent_node` | Kết xuất báo cáo tổng kết, so sánh dữ liệu kết quả với Ground Truth để tính độ chính xác F1-score ở cấp độ cell. | Trả về trạng thái `reporting` |

### 4.2 Định Tuyến Có Điều Kiện (Conditional Edges)

Các hàm định tuyến chính trong [app/graphs/graph.py](file:///d:/Agentic-Data-Cleaner/app/graphs/graph.py):
1. **`route_from_input_validator(state)`**:
   - Nếu `input_validation_result.status == "needs_clarification"` và còn câu hỏi chưa được trả lời → định tuyến tới `END` (Pipeline dừng chờ tương tác người dùng).
   - Nếu sẵn sàng → đi tiếp tới `planner`.
2. **`route_to_current_task(state)`**:
   - Dựa trên danh sách `task_list` được lập bởi planner và index `current_task_idx` hiện tại để trỏ tới worker node tiếp theo: `deduplication`, `null_handling`, `type_casting`.
   - Nếu đã hoàn thành tất cả task trong list → chuyển tới `report_agent`.
3. **`route_from_validator(state)`**:
   - Nếu kết quả validation của task hiện tại **passed**: tăng `current_task_idx` và chuyển sang task tiếp theo (gọi lại `route_to_current_task`).
   - Nếu **failed**: tăng `retry_count`.
     - Nếu `retry_count < max_retries`: quay lại chạy tiếp worker hiện tại để tự sửa sai (Self-correction).
     - Nếu đã cạn lượt retry (`retry_count >= max_retries`): lưu lỗi vào `last_validation_error` và định tuyến quay lại `planner` để replan kế hoạch mới.

### 4.3 Điểm Ngắt HITL (Interrupts) & Luồng Bất Đồng Bộ

Graph được biên dịch với cơ chế ngắt trạng thái (interrupt):
```python
builder.compile(
    checkpointer=checkpointer,
    interrupt_before=["deduplication", "null_handling", "type_casting", "report_agent"]
)
```
*   **HITL-1 (Clarification Checkpoint):** Xảy ra tại `input_validator` nếu phát hiện dữ liệu thiếu rõ ràng, app sẽ dừng graph bằng cách trỏ link tới `END` và chờ frontend submit API `/pipeline/{run_id}/resolve` nhằm nạp câu trả lời của user.
*   **HITL-2 (Plan / Worker Approval Checkpoint):** Trước khi chạy bất kỳ worker làm sạch nào (`deduplication`, `null_handling`, `type_casting`), graph sẽ bị ngắt (interrupt) để người dùng xem xét kế hoạch làm sạch. Khi được phê duyệt qua API `/pipeline/{run_id}/approve_plan`, graph tiếp tục chạy từ vị trí bị dừng (`ainvoke(None)`).
*   **HITL-3 (Final Report Checkpoint):** Interrupt xảy ra trước node `report_agent` để người dùng kiểm duyệt kết quả làm sạch lần cuối.
*   **Luồng Bất đồng bộ & WebSockets:** Hệ thống sử dụng FastAPI `BackgroundTasks` để thực thi pipeline nhằm tránh chặn HTTP request. Đồng thời, `pipeline.py` sử dụng `graph.astream_events` để lọc các sự kiện `on_chain_start`, `on_tool_start`, `on_tool_end` và truyền phát trực tiếp (broadcast) các log này về phía frontend thông qua WebSocket `/ws/{run_id}` thời gian thực.
*   **Cơ chế Đệm (Log Fallback):** Các node lưu vết trạng thái `"Running..."` trước khi hoàn tất vào state, giúp frontend có thể hiển thị trạng thái chuẩn xác ngay cả khi người dùng tải lại trang web hoặc bị rớt kết nối WebSocket.

---

## 5. Trạng Thái Hệ Thống (`GlobalState`)

Được định nghĩa trong [app/graphs/states/global_state.py](file:///d:/Agentic-Data-Cleaner/app/graphs/states/global_state.py). Các state model phụ trợ đã được tách thành các file riêng trong `app/graphs/states/`:

```python
class GlobalState(TypedDict):
    # Core Routing & Messages
    messages: Annotated[list[AnyMessage], add_messages]
    next_node: str | None

    # Project Context
    project_id: str | None
    session_id: str | None
    dataset_path: str | None
    clean_dataset_path: str | None       # ← Đường dẫn dataset sau khi làm sạch
    original_filename: str | None        # ← Tên file gốc người dùng upload
    user_prompt: str | None

    # Data Schema and Requirements
    dataset_schema: dict[str, Any] | None
    dataset_version: str | None
    raw_requirement_input: str | None

    # Data References & Progress
    current_dataset_version: str | None
    physical_dataframe_path: str | None  # ← Cập nhật bởi mỗi worker sau khi ghi file mới
    path_file_to_validate: str | None    # ← Đường dẫn file để validator đọc
    current_step: str | None
    completed_steps: Annotated[list[str], append_list]

    # Intelligence & Validation
    statistical_profile: StatisticalProfile | None
    semantic_profile: SemanticProfile | None
    input_validation_result: InputValidationResult | None

    # Execution & Routing
    execution_plan: ExecutionPlan | None
    task_list: list[str]
    worker_states: WorkerStates | None
    worker_outputs: dict[str, Any] | None  # ← Output chi tiết của từng worker agent
    validation_results: Annotated[list[ValidationResultItem], append_list]
    agent_logs: Annotated[dict[str, Any], merge_agent_logs]  # ← Log từ các Agent gộp dạng dict
    deduplication_result: DeduplicationResult | None  # ← Kết quả riêng của DeduplicationAgent

    # Control flow variables
    current_task_idx: int | None
    retry_count: int | None
    last_validation_error: str | None
    failed_task_id: str | None
    replan_reason: str | None

    # HITL Fields
    hitl_checkpoint: int | None
    hitl_status: Literal["pending", "approved", "rejected"] | None
    hitl_feedback: str | None

    # Global Shared Errors
    global_errors: Annotated[list[str], append_list]

    # Evaluation Metrics
    f1_metrics: dict[str, Any] | None   # ← F1 metric được tính bởi report_agent_node

    # Store original datetime/date formats
    original_datetime_formats: dict[str, dict[str, str]] | None

    # Token Usage Metrics
    token_metrics: Annotated[dict[str, int], sum_metrics]  # ← Quản lý đếm token sử dụng của LLM
```

### State Models Phụ Trợ (các file tách biệt)

| File | Models chính |
| :--- | :--- |
| `input_validation.py` | `InputValidationResult`, `ClarificationIssues`, `NullClarifications` (`extra="allow"` cho per-column Q), `DuplicateClarifications`, `TypecastClarifications`, `StrategyQuestion`, `InsightQuestion`, `ActionPlan`, `AllowMissingConfirmationQuestion` |
| `planning.py` | `ExecutionPlan`, `TaskDetailWrapper` (chứa `work_order: TaskDetail`), `TaskDetail` (chứa `strategy`, `columns`, `outputs`, `skip`) |
| `profiles.py` | `SemanticProfile`, `ColumnSemanticProfileDetail` (chứa `allow_missing`, `expected_type`, `fill_strategies`, `potential_dmv`, v.v.) |
| `profiler_state.py` | `StatisticalProfile`, `ColumnStatProfile` (chứa `null_rate`, `unique_ratio`, `pk_candidates`, `near_unique_columns`, v.v.) |
| `workers.py` | `WorkerStates`, `WorkerStateDetail`, `DeduplicationResult`, `DedupDecisionTrace` |
| `output_validation.py` | `ValidationResultItem`, `TaskVerification`, `ValidationCheck` |

---

## 6. Cấu HÌnh và Đăng Ký Agents

### 6.1 Cơ Chế Khởi Tạo và Cấu Hình LLM

- **BaseAgent class** ([app/agents/base.py](file:///d:/Agentic-Data-Cleaner/app/agents/base.py)):
  Tất cả các agent trong hệ thống đều kế thừa từ `BaseAgent`. Khi khởi tạo, nó tự động tích hợp một `TokenTrackerCallback` và chuyển giao vào hàm `create_llm(callbacks=[self.token_tracker])`. Điều này hỗ trợ việc tích lũy và cập nhật trực tiếp token sử dụng (`token_metrics`) của từng bước xử lý.
- **Cấu hình Model:** 
  Hiện tại, hệ thống lấy cấu hình tập trung từ `.env` thông qua `Settings`:
  - `DEFAULT_LLM_PROVIDER` (mặc định: `openai`)
  - `DEFAULT_LLM_MODEL` (mặc định: `gpt-4o`)
  - `LLM_TEMPERATURE` (mặc định: `0.0`)
- **Tự động Đăng ký Agent:**
  Sử dụng decorator `@AgentRegistry.auto_register` ở đầu mỗi class Agent kế thừa từ `BaseAgent` để đăng ký vào `AgentRegistry` singleton.

### 6.2 Chi Tiết Các Hoạt Động Của Agent

#### A. SemanticProfilerAgent (`semantic_profiler`)
- **File:** [app/agents/semantic_analyzer/profiler_agent.py](file:///d:/Agentic-Data-Cleaner/app/agents/semantic_analyzer/profiler_agent.py)
- **Phương thức hoạt động:** 
  1. Đọc dữ liệu thực tế và lấy ra **10 dòng dữ liệu phổ biến nhất** (`value_counts().head(10)`) kết hợp với profile thống kê EDA làm context.
  2. Sử dụng `structured_llm = self.llm.with_structured_output(CombinedSemanticProfilerOutput)` để buộc LLM phân tích ngữ nghĩa và đưa ra JSON đầu ra chứa thông tin chi tiết của từng cột.
  3. Có cơ chế **Retry Loop (lên đến 3 lần)**: Nếu LLM output thiếu thông tin của bất kỳ cột nào trong schema gốc, Agent sẽ tự động gửi feedback yêu cầu LLM phân tích lại.

#### B. InputValidatorAgent (`input_validator`)
- **File:** [app/agents/input_validator/agent.py](file:///d:/Agentic-Data-Cleaner/app/agents/input_validator/agent.py)
- **Phương thức hoạt động:**
  1. Sử dụng Prompt-based JSON mode để đối chiếu statistical profile và semantic profile với yêu cầu của người dùng.
  2. Sinh ra cấu trúc JSON đầu ra khớp với Pydantic model `InputValidationResult` (parse bằng `model_validate_json`).
  3. **Logic phát hiện 3 loại issues:** NULL, DUPLICATE, TYPECAST.
  4. **Cấu trúc câu hỏi per-issue:**
     - **NULL**: Tạo question riêng cho **từng cột** có null: `Q1_allow_missing_column_<tên_cột>` (Yes/No, không có options) và `Q2_strategy_column_<tên_cột>` (các `fill_strategies` + `fill_llm`/`keep_null` nếu dtype là string/object). `NullClarifications` có `extra="allow"` để chứa các key dynamic.
     - **DUPLICATE**: 3 câu cố định — Q1 (chọn primary key với 3 options), Q2/Q3 (semantic insights).
     - **TYPECAST**: 3 câu cố định — Q1/Q2/Q3 (type mismatch insights với `confirm` yes/no).
  5. **Xử lý sau khi user trả lời:** Phát hiện `is_answered = True` khi tất cả câu hỏi trong `clarifications` đã có `answer`. Khi đó thêm SystemMessage yêu cầu LLM đặt `status = "ready"` và điền `action_plan`.
  6. **`_apply_allow_missing_overrides`:** Sau khi user trả lời, Agent tự động vá `semantic_profile.columns[col].allow_missing` dựa trên câu trả lời "Yes"/"No" của user ở các câu `Q1_allow_missing_column_*`, rồi cập nhật lại `semantic_profile` vào state để planner và các worker sau dùng thông tin đúng.

#### C. PlannerAgent (`planner`)
- **File:** [app/agents/planner/agent.py](file:///d:/Agentic-Data-Cleaner/app/agents/planner/agent.py)
- **Phương thức hoạt động:**
  1. Đọc toàn bộ context dữ liệu, bao gồm các câu trả lời/quyết định của user ở bước Input Validation.
  2. Phân tích xem có cần thực hiện các task dọn dẹp hay không (Deduplication, Null Handling, Type Casting).
  3. Buộc LLM sinh JSON khớp với Pydantic model `ExecutionPlan` chứa danh sách chi tiết các công việc (`task_list`), bao gồm config chiến lược dọn dẹp cụ thể cho từng cột (`strategy`), logic kiểm tra bằng Pandas và các metrics đo lường thành công.

#### D. DeduplicationAgent (`dedup_agent`)
- **File:** [app/agents/deduplication/agent.py](file:///d:/Agentic-Data-Cleaner/app/agents/deduplication/agent.py)
- **Kiến trúc:** Hybrid Sub-agent — LLM chọn strategy + Pandas thực thi tất định.
- **Phương thức hoạt động:**
  1. **Tool Loop (ReAct):** LLM được bind với tool `inspect_duplicate_candidates` (tối đa 3 vòng). Tool này nhận `candidate_column_sets` và trả về `duplicate_count` + `duplicate_group_count` để LLM có bằng chứng thực tế trước khi ra quyết định.
  2. **LLM Decision (JSON mode):** Sau tool loop, LLM sinh `DedupDecision` với `mode` là `exact_full_row` hoặc `exact_key` hoặc `review_needed`, kèm `key_columns`, `confidence`, `reasoning_summary`.
  3. **Validation & Fallback (tất định):** `_validate_dedup_decision` kiểm tra quyết định của LLM qua các bước: Cột bị thiếu, Cột có `null_rate > 30%` bị loại bỏ, ID kỹ thuật đơn lẻ bị downgrade sang `exact_full_row`, confidence thấp thì cảnh báo.
  4. **Fallback Cascade:** planner `strategy.primary_keys` → planner `task.columns` → `statistical_profile.pk_candidates` → `safe_default` (`exact_full_row`).
  5. **Execution (tất định):** Chạy `df.drop_duplicates(keep="first")` cho full-row rồi tiếp tục `drop_duplicates(subset=key_columns)` cho exact-key. Ghi Parquet ra `{project_id}_deduplicated.parquet`.
  6. **Context Hashing:** `_compute_context_hash` tính SHA-256 từ schema, null_rates, pk_candidates, semantic columns, user_prompt và planner task. Nếu hash khớp với lần chạy trước (lưu trong `deduplication_result.decision_trace`), tái sử dụng quyết định cũ, tránh gọi LLM lại.
  7. **Debug Override:** Khi `planner_task.rationale == "Injected by the debug dedup endpoint."`, bỏ qua LLM và dùng cột từ planner task trực tiếp.

#### E. NullAgent (`null_agent`)
- **File:** [app/agents/null_agent/agent.py](file:///d:/Agentic-Data-Cleaner/app/agents/null_agent/agent.py)
- **Kiến trúc:** Deterministic Agent — không dùng LLM.
- **Phương thức hoạt động:**
  1. Đọc `execution_plan` từ state, tìm task có `task_id == "null_handling"`.
  2. Đọc `strategy.per_column` dict từ task — mỗi entry là `{column: {strategy: ..., fill_value: ...}}`.
  3. **Xử lý từng cột theo strategy với các thuật toán nâng cao:**
     - `drop_row`: Xóa toàn bộ row chứa null ở cột đó.
     - `fill_value`: Điền giá trị hằng số (mặc định `"Unknown"`).
     - `fill_mode`: Điền giá trị xuất hiện nhiều nhất (mode).
     - `fill_mean`: Điền giá trị trung bình (Mean) cho cột số hoặc thời gian (Temporal), có thực hiện làm tròn số nguyên nếu là cột Discrete.
     - `fill_median`: Điền giá trị trung vị (Median) cho cột số hoặc thời gian (Temporal).
     - `leave_as_is` / `skip` / `keep_null`: Giữ nguyên không thay đổi.
  4. **Type-Specific Coercions (Ràng buộc đặc thù kiểu dữ liệu):**
     - Cột **Identifier** (mã định danh) không bao giờ được điền (coerced sang `drop_row` hoặc `leave_as_is`).
     - Cột **Structured text** tự động chọn `leave_as_is` hoặc `drop_row` phụ thuộc vào thuộc tính `allow_missing`.
     - Cột **Free text / Geospatial** chỉ hỗ trợ giữ nguyên hoặc điền hằng số `fill_value`.
     - Cột **Ordinal / Boolean** tự động ép các chiến lược Mean/Median về `fill_mode`.
  5. **Bảo vệ toàn vẹn hệ thống:** Cấm tuyệt đối chiến lược xóa cột (`drop_column`), bỏ qua chiến lược gọi LLM (`fill_llm`) chuyển về `leave_as_is`.
  6. **Validate & Fallback Directory:** Kiểm tra ràng buộc `must_preserve_row_count`. Ghi tệp kết quả ra thư mục đầu ra, nếu bị lỗi phân quyền sẽ tự động thử ghi vào thư mục tạm `.tmp/agentic-data-cleaner/outputs`.

#### F. TypeCastingAgent (`typecast_agent`)
- **File:** [app/agents/type_agent/agent.py](file:///d:/Agentic-Data-Cleaner/app/agents/type_agent/agent.py)
- **Kiến trúc:** Deterministic Agent — không dùng LLM.
- **Phương thức hoạt động:**
  1. Đọc `execution_plan` từ state, tìm task có `task_id == "type_casting"`. Nếu `task.skip == True` → trả về skipped update ngay.
  2. **Build Casting Plan (`TypeCastingPlan`):** Xác định kiểu dữ liệu mong đợi của từng cột dựa trên cấu hình Planner, fallback về kì vọng của `semantic_profile`.
  3. **Cast Series (`_cast_series`):** Thực thi ép kiểu nullable sang: `str` (StringDtype), `float` (Float64), `int` (Int64), `bool` (boolean), `datetime` (to_datetime, format="mixed"), `date` (to_datetime + normalize).
  4. **Trích xuất định dạng gốc (Original Datetime Format Extraction):** Với cột kiểu `datetime` hoặc `date`, Agent thực hiện lấy mẫu dòng dữ liệu gốc để trích xuất biểu thức định dạng (`format`) và biểu thức regex định cấu trúc (`regex`), sau đó lưu trữ tập trung vào state `original_datetime_formats`.
  5. **Persistence:** Ghi tệp parquet `{project_id}_type_casted.parquet` và ghi phiên bản lineage mới qua `LineageService.append_new_version`.

---

## 7. PostgreSQL-Backed Lineage Tracking

Thay vì lưu file Parquet ad-hoc cho từng bước xử lý, hệ thống triển khai cơ chế **Data Lineage Tracking** lưu trữ trực tiếp trên PostgreSQL:

- **Database Schema ([app/models/lineage.py](file:///d:/Agentic-Data-Cleaner/app/models/lineage.py)):**
  - **`sessions` table:** Theo dõi mỗi phiên làm việc dọn dẹp của tệp dữ liệu.
  - **`lineage_versions` table:** Ghi lại lịch sử dọn dẹp theo từng phiên bản (`version`), lưu tên tác nhân tác động (`agent_name`) và mô tả hành động (`description`).
  - **`dataset_records` table:** Lưu trữ **dữ liệu thực tế của từng dòng** dưới định dạng **JSONB** (`data` column), kèm chỉ số dòng gốc (`row_index`) để đảm bảo bảo toàn thứ tự dòng.
- **LineageService ([app/services/lineage_service.py](file:///d:/Agentic-Data-Cleaner/app/services/lineage_service.py)):**
  - Cung cấp hàm `append_new_version(session_id, df, agent_name, description)` để lưu một DataFrame mới thành một version tiếp theo trong database.
  - Hàm `get_latest_version(session_id)` giúp truy vấn toàn bộ các record của version mới nhất từ bảng `dataset_records`, sắp xếp theo `row_index` và xuất ra dưới dạng Pandas DataFrame để nạp vào các worker xử lý hoặc validator.
  - Hàm `append_new_version_from_file(session_id, file_path, agent_name, description)` hỗ trợ đọc trực tiếp tệp Parquet và ghi bản ghi phiên bản mới vào database.

---

## 8. Cơ Chế Kiểm Thử Chất Lượng (Validator Node)

Hệ thống sử dụng cơ chế **Kiểm thử Lai (Hybrid Validation)** kết hợp sự nghiêm ngặt của Pandas và khả năng suy luận của LLM (`ValidatorAgent`):

1. **Sinh Luật và Thực thi Kiểm tra Động (`app/tools/data/quality_control/validator.py`):**
   - Đọc cấu hình dọn dẹp từ `TaskDetail` của planner kết hợp với thông tin ngữ nghĩa của `SemanticProfile` để chuyển hóa thành các bước kiểm tra (ví dụ duplicate_rows = 0, null_rate <= X, định dạng cấu trúc expected_str_pattern) chạy trên data gốc bằng Pandas.
   - Hàm `run_pandas_validation` được kích hoạt để trả về kết quả thành công/thất bại chi tiết của các luật Pandas.
2. **Đánh Giá bằng LLM ReAct Loop (`app/agents/result_validators/agent.py`):**
   - Kết quả của Pandas validation được nạp vào context của LLM (cùng với yêu cầu của user và kế hoạch của planner). LLM sau đó có thể gọi tool `perform_data_quality_check` để tự do khám phá thêm data. Cuối cùng, LLM trả về cấu trúc JSON `ValidatorOutput` đánh giá xem data có qua bài test hay không.
3. **Xử lý sau validation thành công:**
   - **Khôi phục định dạng ngày giờ (Restore Datetime Formats):** Nếu task đã hoàn thành là `null_handling` và trong state có lưu `original_datetime_formats`, node `validator_node` sẽ tự động thực hiện khôi phục định dạng ngày tháng hiển thị gốc (ví dụ `YYYY/MM/DD` hoặc có giờ phút giây tương ứng) về tập dữ liệu đã làm sạch để tránh việc trích xuất và biến đổi trước đó làm mất cấu trúc định dạng nguyên bản.
   - **Ghi lineage:** Gọi `LineageService.append_new_version_from_file` lưu lại version được phê duyệt của tác vụ dọn dẹp vào PostgreSQL.

---

## 9. Chi Tiết API Endpoints (FastAPI)

Tắc cả các router được quản lý tập trung trong [app/api/v1/router.py](file:///d:/Agentic-Data-Cleaner/app/api/v1/router.py):

| Method | Path | Description |
| :--- | :--- | :--- |
| **POST** | `/api/v1/pipeline/run` | Nhận file tải lên cùng yêu cầu dọn dẹp của người dùng. Thực hiện Ingestion lưu trữ thô, chuyển đổi thành canonical Parquet, tạo session và khởi động pipeline chạy bất đồng bộ trong background. |
| **GET** | `/api/v1/pipeline/{run_id}/state` | Truy cập trực tiếp Postgres checkpointer để lấy snapshot trạng thái hiện tại của pipeline dọn dẹp. |
| **GET** | `/api/v1/pipeline/{run_id}/download` | Xuất và tải xuống tệp dữ liệu đã xử lý mới nhất dưới các định dạng `csv`, `xlsx` hoặc `parquet`. |
| **GET** | `/api/v1/pipeline/{run_id}/preview` | Trả về preview JSON của tập dữ liệu mới nhất (giới hạn 50 dòng đầu tiên) để hiển thị trên frontend. |
| **POST** | `/api/v1/pipeline/{run_id}/resolve` | Gửi câu trả lời của người dùng cho các câu hỏi clarification của `input_validator` để cập nhật thread state và kích hoạt chạy tiếp pipeline. |
| **POST** | `/api/v1/pipeline/{run_id}/approve_plan` | Gửi tín hiệu phê duyệt kế hoạch làm sạch từ user, khôi phục trạng thái từ checkpoint ngắt hiện tại và tiếp tục chạy pipeline. |
| **POST** | `/api/v1/dedup/run` | Trực tiếp kích hoạt chạy Deduplication Agent đối với một run_id hiện tại (phục vụ mục đích debug/test). |
| **GET** | `/api/v1/health` | API kiểm tra trạng thái liveness hoạt động của hệ thống. |
| **GET** | `/api/v1/readiness` | API kiểm tra trạng thái readiness hoạt động của hệ thống (kiểm tra ping tới Redis cache). |
| **GET** | `/api/v1/ws/{run_id}` / `@app.websocket("/ws/{run_id}")` | Kết nối WebSocket để truyền phát (stream) log thời gian thực từ pipeline về frontend terminal. |

---

## 10. Technical Debt & Cần Cải Thiện Trong Tương Lai

1. **TypeCastingAgent thiếu write fallback dir:** `_write_output_dataframe` của TypeCastingAgent chỉ thử một directory (không có fallback như DeduplicationAgent và NullAgent). Nếu `output_dir` không writable sẽ raise exception.
2. **Reporter Agent chưa dùng LLM:** Agent `reporter` trong `app/agents/reporter/` có prompt nhưng node `report_agent_node` hiện tại chỉ tính F1 metrics nội bộ. Chưa tích hợp `ReporterAgent` vào LangChain/ReAct loop để sinh báo cáo tự nhiên.
3. **Hỗ trợ Multi-file Ingestion:** Backend hiện tại mới chỉ xử lý dọn dẹp đơn file (single session).
4. **InputValidationResult parsing không tolerant:** Nếu LLM sinh ra key dynamic ngoài schema (ví dụ `Q2_strategy_column_SomeName` trong `NullClarifications`), model `NullClarifications` dùng `extra="allow"` để chứa chúng — nhưng các category khác (`DuplicateClarifications`, `TypecastClarifications`) vẫn dùng strict schema cố định.
5. **NullAgent chưa hỗ trợ LLM Imputation:** Chiến lược `fill_llm` hiện bị bỏ qua như một ràng buộc hệ thống (bypassed/ignored) và chưa được tích hợp giải pháp LLM điền khuyết tự động.
