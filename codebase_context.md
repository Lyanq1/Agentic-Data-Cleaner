# Báo Cáo Tổng Hợp Codebase — Agentic Data Engineering

> **Mục đích:** File context toàn diện cho AI (Gemini, Claude, GPT, v.v.) phân tích sâu repository HCMUS Capstone Project.  
> **Ngày cập nhật:** 2026-06-05 (Cập nhật khớp 100% với cấu trúc và code thực tế hiện tại)  
> **Repo:** `Agentic-Data-Cleaner` — Multi-Agent ETL/Data Engineering với Human-In-The-Loop  
> **Package Python:** `app/`

---

## 1. Tóm Tắt Executive

Hệ thống **Agentic Data Engineering** là đồ án tốt nghiệp HCMUS xây dựng pipeline ETL tự động làm sạch dữ liệu dạng bảng (CSV, Excel, JSON) bằng kiến trúc **Multi-Agent** trên **LangGraph**, kết hợp cơ chế kiểm soát chất lượng tự động thông qua **Pandera** và tương tác người dùng **Human-In-The-Loop (HITL)**.

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
[deduplication] ── [validator] (Pandera check & Retry/Replan loop)
   ↓
[null_handling] ── [validator] (Pandera check & Retry/Replan loop)
   ↓
[type_casting]  ── [validator] (Pandera check & Retry/Replan loop)
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
| **Validation Engine**   | Pandera                              | Định nghĩa và check schemas  |
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
│   │   └── states/
│   │       └── global_state.py   # GlobalState TypedDict (LangGraph) & các Pydantic helper models
│   │
│   ├── agents/                   # Thư mục Multi-agent
│   │   ├── __init__.py
│   │   ├── base.py               # Lớp BaseAgent chứa BaseChatModel và bind tools
│   │   ├── roles.py              # Enum AgentRole (profiler, planner, validator, null_agent, v.v.)
│   │   ├── registry.py           # AgentRegistry quản lý đăng ký/khởi tạo Agent tự động
│   │   │
│   │   ├── input_validator/      # Agent kiểm tra input và hỏi clarification
│   │   │   ├── agent.py
│   │   │   └── prompts.py
│   │   │
│   │   ├── planner/              # Agent lập kế hoạch làm sạch
│   │   │   ├── agent.py
│   │   │   └── prompts.py
│   │   │
│   │   ├── semantic_analyzer/    # Agent profiling ngữ nghĩa & audit chất lượng
│   │   │   ├── profiler_agent.py
│   │   │   └── prompts.py
│   │   │
│   │   ├── result_validator/     # Agent validator stub (TODO)
│   │   │   └── agent.py
│   │   │
│   │   └── reporter/             # Agent reporter stub (TODO)
│   │       └── agent.py
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
│   ├── validators/               # Thư viện kiểm chuẩn chất lượng dữ liệu với Pandera
│   │   ├── __init__.py
│   │   ├── models.py             # ValidationOutcome model
│   │   ├── runner.py             # validate_current_task() chạy kiểm thử thực tế trên dataframe
│   │   └── schema_builder.py     # Tự động sinh Pandera Schema động từ profile
│   │
│   ├── services/                 # Business logic services
│   │   ├── __init__.py
│   │   ├── ingestion.py          # IngestionService quản lý validation và lưu trữ ban đầu
│   │   ├── lineage_service.py    # LineageService đọc/ghi version dữ liệu từ Postgres JSONB
│   │   ├── lineage_utils.py
│   │   └── pipeline.py           # run_pipeline(), get_pipeline_state()
│   │
│   └── tools/                    # Các module chứa tool phụ trợ
│       ├── __init__.py
│       ├── tool_registration.py  # Đăng ký tool cho agents
│       └── data/
│           └── eda/              # Tool thực hiện EDA thống kê
│               ├── __init__.py
│               ├── cli.py
│               ├── models.py
│               ├── profiler.py   # StatisticalProfiler phân tích data thô
│               ├── tool.py       # perform_eda LangChain tool
│               └── utils.py
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
| **deduplication** | `deduplication_node` | Node thực hiện dọn dẹp các dòng trùng lặp (hiện tại là worker stub lưu pass-through dữ liệu). | `_persist_passthrough_worker_version` |
| **null_handling** | `null_handling_node` | Node xử lý giá trị khuyết thiếu (hiện tại là worker stub). | `_persist_passthrough_worker_version` |
| **type_casting** | `type_casting_node` | Node chuẩn hóa kiểu dữ liệu theo mong đợi ngữ nghĩa (hiện tại là worker stub). | `_persist_passthrough_worker_version` |
| **validator** | `validator_node` | Kiểm thử chất lượng dữ liệu đầu ra của worker hiện tại bằng Pandera schema sinh tự động. | `validate_current_task()` |
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

Được định nghĩa trong [app/graphs/states/global_state.py](file:///Users/lyanhquan/code/Agentic-Data-Cleaner/app/graphs/states/global_state.py):

```python
class GlobalState(TypedDict):
    # Core Routing & Messages
    messages: Annotated[list[AnyMessage], add_messages]
    next_node: Optional[str]

    # Project Context
    project_id: Optional[str]
    session_id: Optional[str]
    dataset_path: Optional[str]
    user_prompt: Optional[str]

    # Data Schema and Requirements
    dataset_schema: Optional[Dict[str, Any]]
    dataset_version: Optional[str]
    raw_requirement_input: Optional[str]

    # Data References & Progress
    current_dataset_version: Optional[str]
    physical_dataframe_path: Optional[str]
    current_step: Optional[str]
    completed_steps: Annotated[List[str], append_list]

    # Intelligence & Validation
    statistical_profile: Optional[StatisticalProfile]
    semantic_profile: Optional[SemanticProfile]
    input_validation_result: Optional[InputValidationResult]
    
    # Execution & Routing
    execution_plan: Optional[ExecutionPlan]
    task_list: List[str]
    worker_states: Optional[WorkerStates]
    validation_results: Annotated[List[ValidationResultItem], append_list]
    
    # Control flow variables
    current_task_idx: Optional[int]
    retry_count: Optional[int]
    last_validation_error: Optional[str]
    failed_task_id: Optional[str]
    replan_reason: Optional[str]

    # HITL Fields
    hitl_checkpoint: Optional[int]
    hitl_status: Optional[Literal["pending", "approved", "rejected"]]
    hitl_feedback: Optional[str]

    # Global Shared Errors
    global_errors: Annotated[List[str], append_list]
```

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
  1. Sử dụng Prompt-based JSON mode (`self.llm.bind(response_format={"type": "json_object"})`) để đối chiếu các profile chất lượng dữ liệu với mong muốn dọn dẹp của người dùng.
  2. Sinh ra cấu trúc JSON đầu ra khớp với model `InputValidationResult`.
  3. Nếu có các điểm bất hợp lý trong dữ liệu, Agent sinh ra cấu trúc các câu hỏi làm rõ (`clarifications`) chứa các `StrategyQuestion` và `InsightQuestion` có các options cụ thể cho user lựa chọn.
  4. Khi nhận được phản hồi của user từ API, Agent sẽ đọc lại lịch sử chat chứa câu trả lời để chuyển trạng thái thành `ready`, sinh ra `action_plan` và chuyển tiếp luồng tới planner.

#### C. PlannerAgent (`planner`)
- **File:** [app/agents/planner/agent.py](file:///Users/lyanhquan/code/Agentic-Data-Cleaner/app/agents/planner/agent.py)
- **Phương thức hoạt động:**
  1. Đọc toàn bộ context dữ liệu, bao gồm các câu trả lời/quyết định của user ở bước Input Validation.
  2. Phân tích xem có cần thực hiện các task dọn dẹp hay không:
     - **Deduplication:** Nếu có dòng lặp lại hoặc tỷ lệ unique < 1.0 trên cột key.
     - **Null Handling:** Nếu phát hiện null hay disguised missing values.
     - **Type Casting:** Nếu kiểu dữ liệu thực tế sai lệch so với kiểu dữ liệu mong đợi của ngữ nghĩa.
  3. Buộc LLM sinh JSON khớp với Pydantic model `ExecutionPlan` chứa danh sách chi tiết các công việc (`task_list`), bao gồm config chiến lược dọn dẹp cụ thể cho từng cột (`strategy`), logic kiểm tra Pandera và các metrics đo lường thành công.

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

Khác với các tài liệu cũ đề xuất sử dụng LLM để validate kết quả làm sạch, hệ thống hiện tại sử dụng **Pandera Engine** để thực hiện kiểm thử tự động một cách nghiêm ngặt:

1. **Sinh Schema Động (`app/validators/schema_builder.py`):**
   Đọc cấu hình dọn dẹp từ `TaskDetail` của planner kết hợp với thông tin ngữ nghĩa của `SemanticProfile` để tạo ra một `pandera.DataFrameSchema` động phù hợp cho cột cần check.
2. **Thực thi Validate (`app/validators/runner.py`):**
   Hàm `validate_current_task(state)` lấy DataFrame của phiên bản dữ liệu mới nhất từ `LineageService` và thực hiện validate dựa trên schema động đã xây dựng.
3. **Phản hồi lỗi dọn dẹp:**
   Nếu validation thất bại, validator bắt các lỗi `SchemaErrors`, trích xuất các quy tắc kiểm tra bị lỗi (`failed_rules`) và trả về `ValidationOutcome` chứa mã lỗi để graph điều phối thực hiện cơ chế **Self-correction (sửa sai tự động)** hoặc **Re-planning** bởi PlannerAgent.

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

1. **Worker Agents thực sự:** Hiện nay, các node `deduplication`, `null_handling` và `type_casting` mới chỉ là stubs ghi đè dữ liệu pass-through vào database. Cần triển khai các worker thực tế sinh code Pandas hoặc sử dụng thư viện chuyên dụng dựa trên cấu hình `strategy` do planner lập ra.
2. **ResultValidator và Reporter Agents:** Các agent `result_validator` và `reporter` trong thư mục `app/agents/` hiện tại vẫn đang là stubs trả về giá trị TODO. Cần tích hợp chúng sâu vào pipeline LangGraph tương ứng với node `validator` và `report_agent_node`.
3. **Hỗ trợ Multi-file Ingestion:** Mặc dù API endpoints có nhắc đến upload multi-file nhưng backend hiện tại mới chỉ tập trung xử lý dọn dẹp đơn file (single session).
