# Báo Cáo Tổng Hợp Codebase — Agentic Data Engineering

> **Mục đích:** File context toàn diện cho AI (Gemini, Claude, GPT, v.v.) phân tích sâu repository HCMUS Capstone Project.  
> **Ngày cập nhật:** 2026-06-14 (Cập nhật khớp 100% với cấu trúc và code thực tế hiện tại)  
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
| **Language**            | Python                               | >=3.11                       |
| **Agent Orchestration** | LangGraph                            | >=0.1                        |
| **LLM Framework**       | LangChain                            | langchain-core, langchain-openai, langchain-anthropic |
| **LLM Providers**       | OpenAI (mặc định), Anthropic         | Cấu hình qua `.env`          |
| **Data Processing**     | pandas, pyarrow                      | Parquet format cho Ingestion |
| **Validation Engine**   | Custom Pandas Validator              | Thực thi validation rules |
| **Database**            | PostgreSQL                           | Lưu trữ Lineage và dữ liệu   |
| **ORM & Driver**        | SQLAlchemy, psycopg2-binary          | Quản lý kết nối PostgreSQL   |
| **Session Cache**       | Redis                                | Quản lý session              |
| **API Framework**       | FastAPI + Uvicorn                    | Port 8000                    |
| **Frontend**            | React + Vite + TypeScript            | Tailwind CSS, TanStack Query |

---

## 3. Cấu Trúc Thư Mục Chi Tiết Thực Tế

```
Agentic-Data-Cleaner/
├── app/                          # ← BACKEND CHÍNH
│   ├── __init__.py
│   ├── main.py                   # Khởi tạo FastAPI app, lifespan, CORS, routers
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   └── config.py             # Pydantic BaseSettings, load biến môi trường từ .env
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── database.py           # Thiết lập SQLAlchemy engine, SessionLocal, init_db()
│   │   ├── llm_factory.py        # create_llm() chat model ChatOpenAI / ChatAnthropic
│   │   └── redis_client.py       # Quản lý kết nối Redis
│   │
│   ├── exceptions/
│   │   ├── __init__.py
│   │   └── ingestion_exceptions.py  # IngestionError class
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── lineage.py            # SQLAlchemy models: Session, LineageVersion, DatasetRecord
│   │   └── schemas/
│   │
│   ├── graphs/                   # LangGraph pipeline definition
│   │   ├── __init__.py
│   │   ├── graph.py              # build_graph() — Định nghĩa graph, nodes, conditional edges và checkpointer
│   │   ├── nodes.py              # Implementations của các node trong graph
│   │   ├── edges.py              # Logic định tuyến phụ trợ
│   │   ├── checkpointer.py       # AsyncPostgresSaver checkpointer cho LangGraph
│   │   └── states/               # Tách biệt các Pydantic state model theo từng domain
│   │       ├── global_state.py   # GlobalState TypedDict (LangGraph) + append_list helper
│   │       ├── input_validation.py  # InputValidationResult, ClarificationIssues, NullClarifications, StrategyQuestion, InsightQuestion
│   │       ├── planning.py       # ExecutionPlan, TaskDetail, TaskWrapper
│   │       ├── profiles.py       # SemanticProfile, SemanticColumnDetail
│   │       ├── profiler_state.py # StatisticalProfile, StatisticalColumnDetail
│   │       ├── workers.py        # WorkerStates, WorkerStateDetail, DeduplicationResult, DedupDecisionTrace
│   │       └── output_validation.py # ValidationResultItem
│   │
│   ├── agents/                   # Thư mục Multi-agent
│   │   ├── __init__.py
│   │   ├── base.py               # Lớp BaseAgent chứa BaseChatModel và bind tools
│   │   ├── roles.py              # Enum AgentRole (profiler, planner, null_agent, dedup_agent, typecast_agent, v.v.)
│   │   ├── registry.py           # AgentRegistry quản lý đăng ký/khởi tạo Agent tự động
│   │   │
│   │   ├── input_validator/      # Agent kiểm tra input và hỏi clarification
│   │   │   ├── agent.py          # InputValidatorAgent — JSON mode LLM + _apply_allow_missing_overrides
│   │   │   └── prompts.py        # INPUT_VALIDATOR_SYSTEM_PROMPT (3 issues: NULL/DUPLICATE/TYPECAST)
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
│   │   │   ├── agent.py          # DeduplicationAgent — tool loop + validate + execute
│   │   │   ├── models.py         # DedupDecision, ValidatedDedupDecision, DeduplicationAgentInput
│   │   │   └── prompt.py         # build_dedup_messages(), DEDUP_DECISION_JSON_INSTRUCTION
│   │   │
│   │   ├── null_agent/           # Deterministic null handling worker
│   │   │   ├── agent.py          # NullAgent — drop_row / fill_value / leave_as_is strategies
│   │   │   └── __init__.py
│   │   │
│   │   ├── type_agent/           # Deterministic type casting worker
│   │   │   ├── agent.py          # TypeCastingAgent — per_column casting + LineageService
│   │   │   ├── prompts.py
│   │   │   └── __init__.py
│   │   │
│   │   ├── result_validators/    # Hybrid validator agent (Pandas rules + LLM ReAct)
│   │   │   ├── agent.py
│   │   │   ├── models.py
│   │   │   └── prompts.py
│   │   │
│   │   └── reporter/             # Agent báo cáo tổng kết pipeline
│   │       ├── agent.py
│   │       └── prompts.py
│   │
│   ├── ingestion/                # Ingestion pipeline
│   │   ├── __init__.py
│   │   ├── normalizer.py         # ingest_to_canonical() convert file → Parquet + lưu database
│   │   └── parsers/              # Parsers cho các loại file
│   │       ├── base.py
│   │       ├── csv_parser.py
│   │       ├── excel_parser.py
│   │       └── json_parser.py
│   │
│   ├── validators/               # Thư viện kiểm chuẩn chất lượng dữ liệu với Pandas
│   │   ├── __init__.py
│   │   ├── models.py             # ValidationOutcome model
│   │   ├── runner.py             # validate_current_task() chạy kiểm thử thực tế trên dataframe
│   │   └── pandas_validator.py   # Thực thi rule kiểm tra bằng Pandas
│   │
│   ├── services/                 # Business logic services
│   │   ├── __init__.py
│   │   ├── ingestion.py          # IngestionService quản lý validation và lưu trữ ban đầu
│   │   ├── lineage_service.py    # LineageService đọc/ghi version dữ liệu từ Postgres JSONB
│   │   ├── lineage_utils.py      # resolve_lineage_session_id()
│   │   ├── dataframe_order.py    # restore_original_column_order() tiện ích thứ tự cột
│   │   └── pipeline.py           # run_pipeline(), get_pipeline_state()
│   │
│   └── tools/                    # Các module chứa tool phụ trợ
│       ├── __init__.py
│       ├── tool_registration.py  # Đăng ký tool cho agents
│       └── data/
│           ├── eda/              # Tool thực hiện EDA thống kê
│           │   ├── __init__.py
│           │   ├── cli.py
│           │   ├── models.py
│           │   ├── profiler.py   # StatisticalProfiler phân tích data thô
│           │   ├── tool.py       # perform_eda LangChain tool
│           │   └── utils.py
│           ├── dedup/            # Tool hỗ trợ DeduplicationAgent
│           │   ├── __init__.py
│           │   └── tool.py       # @tool inspect_duplicate_candidates — kiểm tra duplicate metrics cho candidate column sets
│           └── quality_control/  # Tool hỗ trợ ValidatorAgent
│               └── validator.py  # perform_data_quality_check
│
├── frontend/                     # React App
├── tests/                        # Hệ thống test
├── docker-compose.yml            # Khởi tạo Postgres + Redis
└── .env                          # Cấu hình môi trường thực tế
```

---

## 4. Kiến Trúc Pipeline LangGraph & Luồng HITL

### 4.1 Chi tiết các Nodes của Pipeline

Hệ thống định nghĩa 9 nodes chính trong [app/graphs/nodes.py](file:///Users/lyanhquan/code/Agentic-Data-Cleaner/app/graphs/nodes.py):

| Node | Tên hàm | Vai trò | Tương tác Agent/Tool |
| :--- | :--- | :--- | :--- |
| **profiler** | `profiler_node` | Chạy EDA thống kê mô tả trên dataset thô, tạo ra profile kỹ thuật cơ bản. | Gọi `@tool perform_eda` |
| **semantic_profile** | `semantic_profile_node` | Phân tích ngữ nghĩa của từng cột, nhóm logic, tìm mối liên hệ, và audit chất lượng dữ liệu ban đầu. | `SemanticProfilerAgent` |
| **input_validator** | `input_validator_node` | Đối chiếu profile thống kê & ngữ nghĩa với yêu cầu làm sạch của người dùng, xác định có cần làm rõ thông tin hay không. | `InputValidatorAgent` |
| **planner** | `planner_node` | Sinh kế hoạch dọn dẹp dữ liệu chi tiết (`ExecutionPlan`) gồm các task cho deduplication, null handling và type casting. | `PlannerAgent` |
| **deduplication** | `deduplication_node` | Tác nhân con lai (Hybrid Sub-agent) sử dụng LLM để chọn chiến lược dedup (exact_key hoặc exact_full_row) kết hợp thực thi tất định bằng Pandas. | `DeduplicationAgent` |
| **null_handling** | `null_handling_node` | Tác nhân tất định (Deterministic Agent) áp dụng các chiến lược điền/xóa null dựa trên cấu hình từ Planner. | `NullAgent` |
| **type_casting** | `type_casting_node` | Tác nhân tất định (Deterministic Agent) ép kiểu dữ liệu dựa trên Semantic Profile và Planner's work order. | `TypeCastingAgent` |
| **validator** | `validator_node` | Tác nhân đánh giá kết quả làm sạch bằng phương pháp lai (Hybrid): Chạy các rule Pandas tất định trước, sau đó dùng LLM (ReAct) để tổng hợp và đánh giá. | `ValidatorAgent`
| **report_agent** | `report_agent_node` | Node xuất báo cáo tổng kết pipeline (hiện tại là stub). | Trả về trạng thái `reporting` |

### 4.2 Định Tuyến Có Điều Kiện (Conditional Edges)

Các hàm định tuyến chính trong [app/graphs/graph.py](file:///Users/lyanhquan/code/Agentic-Data-Cleaner/app/graphs/graph.py):
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

### 4.3 Điểm Ngắt HITL (Interrupts)

Graph được biên dịch với cơ chế ngắt trạng thái (interrupt):
```python
builder.compile(
    checkpointer=checkpointer,
    interrupt_before=["deduplication", "null_handling", "type_casting", "report_agent"]
)
```
- **HITL-1 (Clarification Checkpoint):** Xảy ra tại `input_validator` nếu phát hiện dữ liệu thiếu rõ ràng, app sẽ dừng graph bằng cách trỏ link tới `END` và lưu trạng thái để chờ frontend submit API `/pipeline/{run_id}/resolve` nhằm nạp câu trả lời của user.
- **HITL-2 (Plan / Worker Approval Checkpoint):** Trước khi chạy bất kỳ worker làm sạch nào (`deduplication`, `null_handling`, `type_casting`), graph sẽ bị ngắt (interrupt) để người dùng xem xét kế hoạch làm sạch. Khi được phê duyệt qua API `/pipeline/{run_id}/approve_plan`, graph tiếp tục chạy từ vị trí bị dừng (`ainvoke(None)`).
- **HITL-3 (Final Report Checkpoint):** Interrupt xảy ra trước node `report_agent` để người dùng kiểm duyệt kết quả làm sạch lần cuối.

---

## 5. Trạng Thái Hệ Thống (`GlobalState`)

Được định nghĩa trong [app/graphs/states/global_state.py](file:///Users/lyanhquan/code/Agentic-Data-Cleaner/app/graphs/states/global_state.py). Các state model phụ trợ đã được tách thành các file riêng trong `app/graphs/states/`:

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
    agent_logs: Annotated[list[dict[str, Any]], append_list]  # ← Log từ NullAgent & TypeCastingAgent
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
```

### State Models Phụ Trợ (các file tách biệt)

| File | Models chính |
| :--- | :--- |
| `input_validation.py` | `InputValidationResult`, `ClarificationIssues`, `NullClarifications` (`extra="allow"` cho per-column Q), `DuplicateClarifications`, `TypecastClarifications`, `StrategyQuestion`, `InsightQuestion`, `ActionPlan`, `AllowMissingConfirmationQuestion` |
| `planning.py` | `ExecutionPlan`, `TaskWrapper`, `TaskDetail` (chứa `strategy`, `columns`, `outputs`, `skip`) |
| `profiles.py` | `SemanticProfile`, `SemanticColumnDetail` (chứa `allow_missing`, `expected_type`, `fill_strategies`, `potential_dmv`, v.v.) |
| `profiler_state.py` | `StatisticalProfile`, `StatisticalColumnDetail` (chứa `null_rate`, `unique_ratio`, `pk_candidates`, `near_unique_columns`, v.v.) |
| `workers.py` | `WorkerStates`, `WorkerStateDetail`, `DeduplicationResult`, `DedupDecisionTrace` |
| `output_validation.py` | `ValidationResultItem` |

---

## 6. Cấu Hình và Đăng Ký Agents

### 6.1 Cơ Chế Khởi Tạo và Cấu Hình LLM

- **BaseAgent class** ([app/agents/base.py](file:///Users/lyanhquan/code/Agentic-Data-Cleaner/app/agents/base.py)):
  Tất cả các agent trong hệ thống đều kế thừa từ `BaseAgent`. Khi khởi tạo, nó gọi hàm `create_llm()` từ `app/core/llm_factory.py`.
- **Cấu hình Model:** 
  Hiện tại, hệ thống không chỉ định model cụ thể cho từng Agent ở trong file config Python mà lấy cấu hình tập trung từ `.env` thông qua `Settings`:
  - `DEFAULT_LLM_PROVIDER` (mặc định: `openai`)
  - `DEFAULT_LLM_MODEL` (mặc định: `gpt-4o`)
  - `LLM_TEMPERATURE` (mặc định: `0.0`)
- **Tự động Đăng ký Agent:**
  Sử dụng decorator `@AgentRegistry.auto_register` ở đầu mỗi class Agent kế thừa từ `BaseAgent` để đăng ký vào `AgentRegistry` singleton.

### 6.2 Chi Tiết Các Hoạt Động Của Agent

#### A. SemanticProfilerAgent (`semantic_profiler`)
- **File:** [app/agents/semantic_analyzer/profiler_agent.py](file:///Users/lyanhquan/code/Agentic-Data-Cleaner/app/agents/semantic_analyzer/profiler_agent.py)
- **Phương thức hoạt động:** 
  1. Đọc dữ liệu thực tế và lấy ra **10 dòng dữ liệu phổ biến nhất** (`value_counts().head(10)`) kết hợp với profile thống kê EDA làm context.
  2. Sử dụng `structured_llm = self.llm.with_structured_output(CombinedSemanticProfilerOutput)` để buộc LLM phân tích ngữ nghĩa và đưa ra JSON đầu ra chứa:
     - `table_summary`: Tóm tắt ý nghĩa nghiệp vụ của bảng dữ liệu.
     - `thinking`: CoT giải thích suy luận phân tích.
     - `columns`: Danh sách chi tiết thông tin ngữ nghĩa của từng cột (description, logical_group, expected_type, allow_missing, potential_dmv, expected_str_pattern, và quality review audit như `is_error`, `error_types`, `error_reason`).
  3. Có cơ chế **Retry Loop (lên đến 3 lần)**: Nếu LLM output thiếu thông tin của bất kỳ cột nào trong schema gốc, Agent sẽ tự động gửi feedback yêu cầu LLM phân tích lại.

#### B. InputValidatorAgent (`input_validator`)
- **File:** [app/agents/input_validator/agent.py](file:///Users/lyanhquan/code/Agentic-Data-Cleaner/app/agents/input_validator/agent.py)
- **Phương thức hoạt động:**
  1. Sử dụng Prompt-based JSON mode (`self.llm.bind(response_format={"type": "json_object"})`) để đối chiếu statistical profile và semantic profile với yêu cầu của người dùng.
  2. Sinh ra cấu trúc JSON đầu ra khớp với Pydantic model `InputValidationResult` (parse bằng `model_validate_json`).
  3. **Logic phát hiện 3 loại issues:**
     - **NULL**: `null_count > 0` trong statistical profile HOẶC `potential_dmv` non-empty trong semantic profile.
     - **DUPLICATE**: `duplicate_rows > 0` HOẶC `unique_ratio < 1.0` HOẶC có error_types liên quan.
     - **TYPECAST**: `error_types` chứa `type_mismatch` HOẶC `expected_type` khác `dtype` thực tế.
  4. **Cấu trúc câu hỏi per-issue:**
     - **NULL**: Tạo question riêng cho **từng cột** có null: `Q1_allow_missing_column_<tên_cột>` (Yes/No, không có options) và `Q2_strategy_column_<tên_cột>` (các `fill_strategies` từ semantic profile + `fill_llm`/`keep_null` nếu dtype là string/object). `NullClarifications` có `extra="allow"` để chứa các key dynamic.
     - **DUPLICATE**: 3 câu cố định — Q1 (chọn primary key với 3 options), Q2/Q3 (semantic insights).
     - **TYPECAST**: 3 câu cố định — Q1/Q2/Q3 (type mismatch insights với `confirm` yes/no).
  5. **Xử lý sau khi user trả lời:** Phát hiện `is_answered = True` khi tất cả câu hỏi trong `clarifications` đã có `answer`. Khi đó thêm SystemMessage yêu cầu LLM đặt `status = "ready"` và điền `action_plan`.
  6. **`_apply_allow_missing_overrides`:** Sau khi user trả lời, Agent tự động vá `semantic_profile.columns[col].allow_missing` dựa trên câu trả lời "Yes"/"No" của user ở các câu `Q1_allow_missing_column_*`, rồi cập nhật lại `semantic_profile` vào state để planner và các worker sau dùng thông tin đúng.

#### C. PlannerAgent (`planner`)
- **File:** [app/agents/planner/agent.py](file:///Users/lyanhquan/code/Agentic-Data-Cleaner/app/agents/planner/agent.py)
- **Phương thức hoạt động:**
  1. Đọc toàn bộ context dữ liệu, bao gồm các câu trả lời/quyết định của user ở bước Input Validation.
  2. Phân tích xem có cần thực hiện các task dọn dẹp hay không:
     - **Deduplication:** Nếu có dòng lặp lại hoặc tỷ lệ unique < 1.0 trên cột key.
     - **Null Handling:** Nếu phát hiện null hay disguised missing values.
     - **Type Casting:** Nếu kiểu dữ liệu thực tế sai lệch so với kiểu dữ liệu mong đợi của ngữ nghĩa.
  3. Buộc LLM sinh JSON khớp với Pydantic model `ExecutionPlan` chứa danh sách chi tiết các công việc (`task_list`), bao gồm config chiến lược dọn dẹp cụ thể cho từng cột (`strategy`), logic kiểm tra bằng Pandas và các metrics đo lường thành công.

#### D. DeduplicationAgent (`dedup_agent`)
- **File:** [app/agents/deduplication/agent.py](file:///Users/lyanhquan/code/Agentic-Data-Cleaner/app/agents/deduplication/agent.py)
- **Kiến trúc:** Hybrid Sub-agent — LLM chọn strategy + Pandas thực thi tất định.
- **Phương thức hoạt động:**
  1. **Tool Loop (ReAct):** LLM được bind với tool `inspect_duplicate_candidates` (tối đa 3 vòng). Tool này nhận `candidate_column_sets` và trả về `duplicate_count` + `duplicate_group_count` để LLM có bằng chứng thực tế trước khi ra quyết định.
  2. **LLM Decision (JSON mode):** Sau tool loop, LLM sinh `DedupDecision` với `mode` là `exact_full_row` hoặc `exact_key` hoặc `review_needed`, kèm `key_columns`, `confidence`, `reasoning_summary`.
  3. **Validation & Fallback (tất định):** `_validate_dedup_decision` kiểm tra quyết định của LLM qua các bước:
     - Cột bị thiếu trong DataFrame → fallback.
     - Cột có `null_rate > 30%` → bị loại khỏi key set.
     - Single-column technical ID (kết thúc bằng `_id`, logic group "identity") → downgrade sang `exact_full_row`.
     - `confidence < 0.6` → log warning nhưng vẫn dùng.
     - Fallback cascade: planner `strategy.primary_keys` → planner `task.columns` → `statistical_profile.pk_candidates` → `safe_default` (`exact_full_row`).
  4. **Execution (tất định):** `_execute_validated_decision` chạy `df.drop_duplicates(keep="first")` cho full-row rồi tiếp tục `drop_duplicates(subset=key_columns)` cho exact-key. Ghi Parquet ra `{project_id}_deduplicated.parquet`.
  5. **Context Hashing:** `_compute_context_hash` tính SHA-256 từ schema, null_rates, pk_candidates, semantic columns, user_prompt và planner task. Nếu hash khớp với lần chạy trước (lưu trong `deduplication_result.decision_trace`), tái sử dụng quyết định cũ, tránh gọi LLM lại.
  6. **Debug Override:** Khi `planner_task.rationale == "Injected by the debug dedup endpoint."`, bỏ qua LLM và dùng cột từ planner task trực tiếp.
- **Output state fields:** `deduplication_result`, `physical_dataframe_path`, `current_dataset_version = "deduplication_v1"`, `worker_states.dedup_agent`.

#### E. NullAgent (`null_agent`)
- **File:** [app/agents/null_agent/agent.py](file:///Users/lyanhquan/code/Agentic-Data-Cleaner/app/agents/null_agent/agent.py)
- **Kiến trúc:** Deterministic Agent — không dùng LLM, không có `__init__` gọi `super()`.
- **Phương thức hoạt động:**
  1. Đọc `execution_plan` từ state, tìm task có `task_id == "null_handling"`.
  2. Đọc `strategy.per_column` dict từ task — mỗi entry là `{column: {strategy: ..., fill_value: ...}}`.
  3. **Xử lý từng cột theo strategy:**
     - `drop_row`: Xóa toàn bộ row chứa null ở cột đó, log số row bị drop.
     - `fill_value`: Fill null bằng `cfg["fill_value"]` (default `"Unknown"`), log số cell được fill.
     - `leave_as_is` / `skip`: Giữ nguyên null, ghi vào `skipped_columns`.
     - Bất kỳ strategy không nhận dạng được → xử lý như `leave_as_is`.
  4. **Validate output:** Kiểm tra row count không tăng; nếu planner set `outputs.must_preserve_row_count=True` mà vẫn drop rows → fail.
  5. Ghi Parquet ra `{project_id}_null_handled.parquet` với fallback dir.
- **Output state fields:** `worker_outputs["null_agent"]`, `physical_dataframe_path`, `current_dataset_version = "null_handling_v1"`, `worker_states.null_agent`, `agent_logs`.

#### F. TypeCastingAgent (`typecast_agent`)
- **File:** [app/agents/type_agent/agent.py](file:///Users/lyanhquan/code/Agentic-Data-Cleaner/app/agents/type_agent/agent.py)
- **Kiến trúc:** Deterministic Agent — không dùng LLM.
- **Phương thức hoạt động:**
  1. Đọc `execution_plan` từ state, tìm task có `task_id == "type_casting"`. Nếu `task.skip == True` → trả về skipped update ngay.
  2. **Build Casting Plan (`TypeCastingPlan`):**
     - Ưu tiên 1: `execution_plan.strategy.per_column[col]["expected_type"]`
     - Ưu tiên 2 (fallback): `execution_plan.columns` + `semantic_profile.columns[col].expected_type`
  3. **Normalize expected_type:** Aliases — `integer`→`int`, `double`→`float`, `timestamp`→`datetime`, `boolean`→`bool`, v.v. Chỉ chấp nhận: `{"int", "float", "str", "bool", "date", "datetime"}`.
  4. **`_cast_series` cho từng cột:**
     - `str`: `astype("string")` → pandas StringDtype nullable.
     - `float`: `_normalize_numeric_values` (strip commas, extract regex `[-+]?\d*\.?\d+`) → `pd.to_numeric(errors="coerce").astype("Float64")` nullable.
     - `int`: Như float, thêm bước round nếu có fractional → `astype("Int64")` nullable.
     - `bool`: `_parse_bool` map (`true/yes/y/1` → True, `false/no/n/0` → False, else None) → `astype("boolean")` nullable.
     - `datetime`: `pd.to_datetime(errors="coerce", format="mixed")`.
     - `date`: Như datetime + `.dt.normalize()`.
  5. Tính `coerced_nulls` (số giá trị bị coerce thành null sau cast) cho từng cột, append vào `notes`.
  6. Ghi Parquet `{project_id}_type_casted.parquet` và **gọi `LineageService.append_new_version()`** để lưu version mới vào PostgreSQL.
  7. Đọc dataframe từ `physical_dataframe_path` hoặc fallback sang `LineageService.get_latest_version(session_id)` nếu path không có.
- **Output state fields:** `worker_outputs[typecast_agent]`, `physical_dataframe_path`, `dataset_version` (lineage version number), `current_dataset_version`, `worker_states.typecast_agent`.

---

## 7. PostgreSQL-Backed Lineage Tracking

Thay vì lưu file Parquet ad-hoc cho từng bước xử lý, hệ thống triển khai cơ chế **Data Lineage Tracking** lưu trữ trực tiếp trên PostgreSQL:

- **Database Schema ([app/models/lineage.py](file:///Users/lyanhquan/code/Agentic-Data-Cleaner/app/models/lineage.py)):**
  - **`sessions` table:** Theo dõi mỗi phiên làm việc dọn dẹp của tệp dữ liệu.
  - **`lineage_versions` table:** Ghi lại lịch sử dọn dẹp theo từng phiên bản (`version`), lưu tên tác nhân tác động (`agent_name`) và mô tả hành động (`description`).
  - **`dataset_records` table:** Lưu trữ **dữ liệu thực tế của từng dòng** dưới định dạng **JSONB** (`data` column), kèm chỉ số dòng gốc (`row_index`) để đảm bảo bảo toàn thứ tự dòng.
- **LineageService ([app/services/lineage_service.py](file:///Users/lyanhquan/code/Agentic-Data-Cleaner/app/services/lineage_service.py)):**
  - Cung cấp hàm `append_new_version(session_id, df, agent_name, description)` để lưu một DataFrame mới thành một version tiếp theo trong database.
  - Hàm `get_latest_version(session_id)` giúp truy vấn toàn bộ các record của version mới nhất từ bảng `dataset_records`, sắp xếp theo `row_index` và xuất ra dưới dạng Pandas DataFrame để nạp vào các worker xử lý hoặc validator.

---

## 8. Cơ Chế Kiểm Thử Chất Lượng (Validator Node)

Hệ thống sử dụng cơ chế **Kiểm thử Lai (Hybrid Validation)** kết hợp sự nghiêm ngặt của Pandas và khả năng suy luận của LLM (`ValidatorAgent`):

1. **Sinh Luật và Thực thi Kiểm tra Động (`app/tools/data/quality_control/validator.py`):**
   Đọc cấu hình dọn dẹp từ `TaskDetail` của planner kết hợp với thông tin ngữ nghĩa của `SemanticProfile` để chuyển hóa thành các bước kiểm tra (ví dụ duplicate_rows = 0, null_rate <= X) chạy trên data gốc bằng Pandas.
2. **Đánh Giá bằng LLM ReAct Loop (`app/agents/result_validators/agent.py`):**
   Kết quả của Pandas validation được nạp vào context của LLM (cùng với yêu cầu của user và kế hoạch của planner). LLM sau đó có thể gọi tool `perform_data_quality_check` để tự do khám phá thêm data. Cuối cùng, LLM trả về cấu trúc JSON `ValidatorOutput` đánh giá xem data có qua bài test hay không.
3. **Phản hồi lỗi dọn dẹp:**
   Nếu validation thất bại, node này trả về các rules bị lỗi để graph điều phối thực hiện cơ chế **Self-correction (sửa sai tự động)** (gọi lại worker) hoặc **Re-planning** bởi PlannerAgent.

---

## 9. Chi Tiết API Endpoints (FastAPI)

Tất cả các router được quản lý tập trung trong [app/api/v1/pipeline.py](file:///Users/lyanhquan/code/Agentic-Data-Cleaner/app/api/v1/pipeline.py):

| Method | Path | Description |
| :--- | :--- | :--- |
| **POST** | `/api/v1/pipeline/run` | Nhận file tải lên cùng yêu cầu dọn dẹp của người dùng. Thực hiện Ingestion lưu trữ thô, chuyển đổi thành canonical Parquet, tạo session và khởi động pipeline chạy bất đồng bộ trong background. |
| **GET** | `/api/v1/pipeline/{run_id}/state` | Truy cập trực tiếp Postgres checkpointer để lấy snapshot trạng thái hiện tại của pipeline dọn dẹp. |
| **POST** | `/api/v1/pipeline/{run_id}/resolve` | Gửi câu trả lời của người dùng cho các câu hỏi clarification của `input_validator` để cập nhật thread state và kích hoạt chạy tiếp pipeline. |
| **POST** | `/api/v1/pipeline/{run_id}/approve_plan` | Gửi tín hiệu phê duyệt kế hoạch làm sạch từ user, khôi phục trạng thái từ checkpoint ngắt hiện tại và tiếp tục chạy pipeline. |
| **GET** | `/api/v1/health` | API kiểm tra trạng thái hoạt động của hệ thống. |

---

## 10. Technical Debt & Cần Cải Thiện Trong Tương Lai

1. **NullAgent thiếu các chiến lược nâng cao:** Hiện `NullAgent` chỉ hỗ trợ 3 strategies: `drop_row`, `fill_value`, `leave_as_is`. Các chiến lược nâng cao như `fill_mean`, `fill_median`, `fill_mode`, `fill_llm` (LLM imputation) chưa được triển khai — khi planner sinh ra các strategy này, NullAgent sẽ xử lý chúng như `leave_as_is` (unknown strategy fallback).
2. **TypeCastingAgent thiếu write fallback dir:** `_write_output_dataframe` của TypeCastingAgent chỉ thử một directory (không có fallback như DeduplicationAgent và NullAgent). Nếu `output_dir` không writable sẽ raise exception.
3. **Reporter Agent chưa dùng LLM:** Agent `reporter` trong `app/agents/reporter/` có prompt nhưng node `report_agent_node` hiện tại chỉ tính F1 metrics nội bộ. Chưa tích hợp `ReporterAgent` vào LangChain/ReAct loop để sinh báo cáo tự nhiên.
4. **Hỗ trợ Multi-file Ingestion:** Backend hiện tại mới chỉ xử lý dọn dẹp đơn file (single session).
5. **InputValidationResult parsing không tolerant:** Nếu LLM sinh ra key dynamic ngoài schema (ví dụ `Q2_strategy_column_SomeName` trong `NullClarifications`), model `NullClarifications` dùng `extra="allow"` để chứa chúng — nhưng các category khác (`DuplicateClarifications`, `TypecastClarifications`) vẫn dùng strict schema cố định.

