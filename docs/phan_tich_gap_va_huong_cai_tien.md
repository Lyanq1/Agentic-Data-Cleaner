# Phân Tích Gap & Hướng Cải Thiện Đề Tài

> **Đề tài:** Ứng dụng AI Agents trong Kỹ thuật Xử lý Dữ liệu  
> **Hệ thống:** Agentic Data Cleaner  
> **Ngày:** 07/2026  
> **Mục đích:** Map outline báo cáo → gap so với paper → cải thiện cụ thể → đánh giá mức đóng góp (publish vs vận dụng)

---

## Mục lục

1. [Map outline báo cáo → hiện trạng codebase](#1-map-outline-báo-cáo--hiện-trạng-codebase)
2. [Bảng so sánh với các hệ thống/papers](#2-bảng-so-sánh-với-các-hệ-thốngpapers)
3. [Hai góc nhìn đánh giá: View 1 vs View 2](#3-hai-góc-nhìn-đánh-giá-view-1-vs-view-2)
4. [MAS: đã áp dụng gì, thiếu gì](#4-mas-đã-áp-dụng-gì-thiếu-gì)
5. [Cải thiện theo từng mục báo cáo (1→5)](#5-cải-thiện-theo-từng-mục-báo-cáo-15)
6. [Memory — thiết kế, chứng minh, trade-off](#6-memory--thiết-kế-chứng-minh-trade-off)
7. [Use case metadata — bỏ Input Validator](#7-use-case-metadata--bỏ-input-validator)
8. [Auto mode & benchmark scenarios](#8-auto-mode--benchmark-scenarios)
9. [Chọn model — cost vs quality](#9-chọn-model--cost-vs-quality)
10. [Bảng đánh giá đóng góp (publish hay vận dụng?)](#10-bảng-đánh-giá-đóng-góp-publish-hay-vận-dụng)
11. [Roadmap ưu tiên (2–4 tuần)](#11-roadmap-ưu-tiên-24-tuần)

---

## 1. Map outline báo cáo → hiện trạng codebase

| # Outline báo cáo | Yêu cầu | Codebase hiện tại | Gap |
|-------------------|---------|-------------------|-----|
| **1. Nghiên cứu hiện trạng & nền tảng** | Cơ sở NC, MAS, storage, transform | Ch.2 báo cáo khá đầy đủ | Thiếu khảo sát thực tế; Pandera sai so với code |
| **2. Mô tả bài toán & yêu cầu** | Problem statement đầy đủ | 18 UC, gap analysis | Chưa lập luận "tại sao MAS"; thiếu persona user |
| **3. Giải pháp** | Kiến trúc, agent, flow, implement | LangGraph 9 node, HITL, lineage | Semantic Profiler thiếu mục thiết kế; Ch.5 trống 5.7–5.9 |
| **4. Thực nghiệm** | Dataset, benchmark, bàn luận, chọn model | Có `benchmark_run`, F1, MassUpload | Ch.6 placeholder; thiếu ablation model; thiếu per-component eval |
| **5. Sáng tạo / đóng góp** | So paper, publish potential | Chưa viết rõ | Cần bảng đóng góp từng module; positioning vs AutoDC/Cocoon |

---

## 2. Bảng so sánh với các hệ thống/papers

### 2.1. Landscape (tóm tắt từ literature)

| Hệ thống | Năm | Kiến trúc | LLM? | Workflow | HITL | Benchmark | Metrics chính |
|----------|-----|-----------|------|----------|------|-----------|---------------|
| **HoloClean** | 2017 | ML + probabilistic inference | Không | Rule/ML repair | Không | Hospital, Flights, Food | P, R, F1 (cell) |
| **Raha + Baran** | 2019+ | Ensemble detectors + semi-supervised | Không | Config-free DC | Interactive label | Hospital, Movies, Address | P, R, F1 |
| **CleanAgent** | 2024 | Single LLM agent + declarative API | Có | Standardization tasks | Không | Custom | Task success |
| **Cocoon** | 2024 | Semantic profiling 3 bước + cleaning workflow | Có | Decomposed (context→profile→review) | Có (review) | 5 benchmark (Hospital, Flights, …) | P, R, F1 |
| **AutoDCWorkflow** | 2025 (EMNLP Findings) | 3 LLM agents + OpenRefine | Có | Purpose-driven ops | Không | 96 tables, 142 purposes | Purpose Answer, Column Value, Workflow ops |
| **LLMClean / RetClean** | 2024 | LLM for DC | Có | Single/multi step | Không | Limited | Repair accuracy |
| **Đề tài (Agentic Data Cleaner)** | 2026 | LangGraph 9-node MAS | Có | Task-driven (dedup→null→type) | **3 điểm** (Q&A, plan, result) | Hospital (repo); 6 dataset (báo cáo) | Cell F1, token, latency |

*Nguồn tham khảo: [AutoDCWorkflow (EMNLP 2025)](https://aclanthology.org/2025.findings-emnlp.410/), [Cocoon](https://arxiv.org/abs/2404.12552), [Cocoon cleaning paper](https://arxiv.org/html/2410.15547), [HoloClean VLDB](https://www.vldb.org/pvldb/vol10/p1190-rekatsinas.pdf), [ELT-Bench](https://www.vldb.org/pvldb/vol19/p84-jin.pdf).*

### 2.2. Ai đã làm gì giống bạn?

| Khía cạnh | Ai làm rồi? | Bạn khác ở đâu? |
|-----------|-------------|------------------|
| LLM semantic profiling | **Cocoon** (Context→Profile→Review) | Bạn tách **Statistical Profiler (Pandas)** + **Semantic Profiler (LLM)** — tương tự Cocoon nhưng orchestrate bằng LangGraph |
| Multi-agent cleaning | **AutoDCWorkflow** (3 agents: select cols → inspect → generate ops) | Bạn có **nhiều agent hơn** (8 agents), có **worker deterministic** + **validator loop** |
| LangGraph pipeline | Nhiều repo demo (Agentic-Cleanse, LangGraph cleaning) | Bạn có **HITL checkpoint Postgres**, **lineage versioning**, **benchmark mode** |
| Hybrid validation | Hiếm paper formalize | **Pandas rules + LLM ReAct** + retry/replan — có thể claim nếu chứng minh bằng ablation |
| Auto-resolve benchmark | Cocoon/AutoDC có GT workflow | Bạn có `resolve_benchmark_clarifications()` — **planner không đọc GT** (methodology đúng) |
| Memory across runs | mem0, LangGraph Store (ecosystem) | Bạn **chưa có** — chỉ `context_hash` dedup trong 1 run |

### 2.3. Kết luận positioning

> **Không phải "chỉ nghiên cứu vận dụng thuần túy"** — nhưng cũng **chưa đủ mạnh để claim paper top-tier** nếu không bổ sung thực nghiệm + 1–2 đóng góp được chứng minh.

**Claim hợp lý cho đồ án:**
- *"Integrated multi-agent ETL pipeline with structured HITL, hybrid validation, and reproducible benchmark methodology"*

**Claim cần chứng minh thêm mới dám publish:**
- *"Hybrid validation reduces false replan vs LLM-only"*
- *"Cross-run agent memory improves planner accuracy on repeated schemas"*
- *"Metadata-aware mode reduces HITL friction without accuracy loss"*

---

## 3. Hai góc nhìn đánh giá: View 1 vs View 2

Bạn đã nêu đúng 2 view — đây là cách formalize cho báo cáo:

### View 1 — Bài toán ứng dụng (Production / Interactive)

**Mục tiêu:** Hệ thống usable, linh hoạt, user kiểm soát.

| Khía cạnh | Thiết kế eval |
|-----------|---------------|
| Input | Dirty file + optional prompt + optional metadata |
| Flow | Interactive + HITL (Q&A → plan → result) |
| Metrics | Task completion rate, số câu HITL, thời gian user, subjective UX |
| So sánh | Manual cleaning, ChatGPT one-shot script, OpenRefine |
| **Không cần** | Hardcode transform giống GT 100% |

**Cải thiện cần làm:**
- Thêm **mode metadata**: nếu upload kèm schema JSON / data dictionary → skip Q&A
- Đo **time-to-clean** vs thủ công trên 3–5 dataset thực tế
- Case study 1 pipeline end-to-end có screenshot HITL

### View 2 — Bài toán kiểm định benchmark (Scientific comparison)

**Mục tiêu:** So sánh công bằng với Cocoon, HoloClean, AutoDC trên cùng GT.

| Khía cạnh | Thiết kế eval |
|-----------|---------------|
| Input | Dirty + ground truth (GT không leak vào planner) |
| Flow | `benchmark_run` + auto-resolver |
| Metrics | Cell P/R/F1 (giống HoloClean/Cocoon), + token cost |
| **Cần** | Normalization rules trước compare (format datetime, am/pm, strip, case) |

#### Vấn đề bạn nêu: "Hardcode transform giống GT mới compare được"

**Phân tích:**

Đúng một phần. GT benchmark (Hospital, Flights…) thường có **quy ước format cố định** mà hệ thống cleaning phải "đoán" đúng mới khớp cell-by-cell. Ví dụ:
- `"3:00 PM"` vs `"15:00:00"`
- `"Dr."` vs `"Dr"`
- Leading zeros trong mã bệnh nhân

**Giải pháp 2 tầng (khuyến nghị ghi trong báo cáo):**

```
Tầng A — Cleaning accuracy (năng lực agent)
  → So sánh semantic equivalence, không chỉ string exact match
  → Dùng hàm normalize() trước khi tính F1 (code đã có trong report_agent_node)

Tầng B — Benchmark alignment (so với paper)
  → Tách scenario per error type: S-DUP, S-NULL, S-TYPE, S-FORMAT
  → Với S-FORMAT: document rõ rule chuẩn hóa (am/pm, date format) lấy từ GT
  → Không "hardcode cheat" vào planner — chỉ apply ở evaluation layer
```

**Scenario benchmark đề xuất (Ch.6):**

| Scenario | Dataset | Lỗi focus | Auto-resolver | So sánh với |
|----------|---------|-----------|---------------|-------------|
| S1-full | Hospital | All | ON | Cocoon F1 (paper) |
| S2-dedup-only | Hospital (subset) | Duplicate | ON | HoloClean recall dup |
| S3-null-only | Hospital (subset) | Null/DMV | ON | Baran null repair |
| S4-interactive | Hospital | All | OFF (user mock) | View 1 UX |
| S5-no-HITL | Hospital | All | ON + auto-approve plan | Upper bound throughput |

---

## 4. MAS: đã áp dụng gì, thiếu gì

### 4.1. Pattern MAS đã có trong design

| Pattern MAS | Áp dụng ở đâu | Paper tương đương |
|-------------|---------------|------------------|
| **Blackboard / Shared State** | `GlobalState` TypedDict, mọi agent đọc/ghi | AutoDCWorkflow intermediate table T_i |
| **Supervisor routing** | 3 conditional edges LangGraph | LangGraph supervisor-worker |
| **Specialist workers** | Dedup, Null, TypeCast (deterministic) | AutoDCWorkflow OpenRefine ops |
| **Planner-Executor** | PlannerAgent → workers | AutoDCWorkflow 3-stage |
| **Critic / Validator** | ValidatorAgent + Pandas rules | Cocoon Semantic Review |
| **HITL gates** | interrupt_before + Postgres checkpointer | Cocoon user review; LanG dual checkpoint |
| **Retry / Replan loop** | validator → worker hoặc planner | Agentic self-healing pipelines |
| **Planning** | ExecutionPlan JSON + skill file | AutoDC purpose-driven planning |
| **Memory (hạn chế)** | `context_hash` dedup reuse trong 1 run | Chưa có cross-run memory |

### 4.2. Thiếu so với MAS literature

| Thành phần | Trạng thái | Cải thiện |
|------------|------------|-----------|
| **Long-term memory** | Chưa có | Xem mục 6 |
| **Episodic memory (case bank)** | Chưa có | Lưu (schema_hash → successful ExecutionPlan) |
| **Tool registry dynamic** | Có cơ bản | Document trong báo cáo |
| **Multi-table / star schema** | Không | Hạn chế — ghi rõ Ch.7 |
| **Purpose-driven cleaning** | Không (task-driven) | Khác AutoDC — không phải bug, là design choice |

---

## 5. Cải thiện theo từng mục báo cáo (1→5)

### Mục 1 — Nghiên cứu hiện trạng & nền tảng

**Cải thiện:**

1. **Bổ sung bảng taxonomy** (1 trang):

```
Traditional ML (HoloClean, Raha)
  → Single LLM (CleanAgent, LLMClean)
    → Decomposed LLM (Cocoon)
      → Multi-Agent Orchestrated (AutoDCWorkflow, ĐỀ TÀI)
```

2. **Sửa Pandera → Custom Pandas Validator** trên toàn báo cáo.

3. **Thêm mục 1.x "Tiêu chí chọn nền tảng"** — tại sao LangGraph (interrupt, checkpointer, conditional routing) thay vì LangChain AgentExecutor đơn.

4. **Storage/transform:** document Parquet canonical + PostgreSQL lineage JSONB — đối chiếu với "medallion architecture" lite.

### Mục 2 — Mô tả bài toán

**Cải thiện:**

1. **Formal problem statement:**

> Cho dataset D bẩn, metadata M (optional), user intent I (optional).  
> Tìm D' sao cho quality(D') ≥ θ và D' phản ánh intent I,  
> với traceability qua lineage và human approval tại các decision point.

2. **Persona:** data analyst SME, KTV ETL junior, researcher benchmark.

3. **Functional requirements** — giữ 18 UC, thêm **UC-19: Metadata-first mode**.

4. **Non-functional:** thêm metric **Cost per clean (USD)**, **Replan rate**.

### Mục 3 — Giải pháp

**3a. Thiết kế cơ bản — bổ sung:**

- Sơ đồ **agent taxonomy**: LLM agents vs deterministic workers
- Pattern: **Plan-Validate-Execute loop** (khác AutoDC là Plan-Execute-Inspect iteratively)
- Thêm mục **4.4.x Semantic Profiler Agent**

**3b. Thiết kế chi tiết — bổ sung:**

- Sequence diagram **2 mode**: interactive vs benchmark
- State machine HITL (3 trạng thái: needs_clarification → awaiting_plan → awaiting_result)
- **Evaluation normalization layer** (View 2)

**3c. Thiết kế cài đặt — viết 5.7–5.12** (xem doc `huong_dan_chinh_sua_bao_cao_tot_nghiep.md`)

### Mục 4 — Thực nghiệm (quan trọng nhất)

**Khung eval đa chiều (khuyến nghị):**

| Chiều | Metrics | Nguồn |
|-------|---------|-------|
| **Correctness** | Cell P/R/F1, accuracy | `report_agent_node` |
| **Efficiency** | E2E time, time/node | agent_logs |
| **Cost** | tokens, USD | token_metrics |
| **Reliability** | completion rate, replan count, retry count | state |
| **Usability** | # HITL questions, user wait time | interactive runs |
| **Trajectory** | steps to success, tool call accuracy | LangSmith (optional) |

**Per-component eval (bạn yêu cầu "kết quả từng thành phần"):**

| Component | Đo gì | Cách đo |
|-----------|-------|---------|
| Statistical Profiler | null_rate accuracy vs GT profile | So sánh profile output |
| Semantic Profiler | semantic_type accuracy | Manual label 20 columns |
| Input Validator | clarification necessity rate | % run cần HITL / tổng |
| Planner | plan validity (schema pass) | % plan pass Pydantic + validator first pass |
| Dedup Agent | duplicate removal recall | rows removed vs GT diff |
| Null Agent | null repair recall | cells fixed vs GT |
| Type Agent | cast accuracy | dtype match vs GT |
| Validator | false pass / false fail | Manual audit 50 cells |
| **Full pipeline** | F1 | benchmark mode |

**So benchmark với paper (Hospital):**

| Method | F1 (reported) | Ghi chú |
|--------|---------------|---------|
| HoloClean | ~0.85 P, ~0.71 R (Hospital) | VLDB 2017 |
| Cocoon | "outperforms SOTA on most benchmarks" | arXiv 2410.15547 — lấy số từ Table 1 paper |
| AutoDCWorkflow | Column Value similarity | EMNLP 2025 — metric khác, cần convert |
| **Đề tài (S2 benchmark)** | *chạy và điền* | Cell F1, cùng Hospital dataset |

> **Tại sao F1 có thể cao hơn một chút?** — Viết trong "Bàn luận" nếu đúng:
> - Deterministic workers → ít hallucination hơn single LLM code gen
> - Validation loop bắt lỗi sớm
> - Auto-resolver trả lời đúng strategy từ GT (benchmark mode — **không áp dụng cho View 1**)
> - Hospital có nhiều duplicate → dedup exact_key mạnh

### Mục 5 — Sáng tạo & đóng góp

Xem **Bảng mục 10** bên dưới.

---

## 6. Memory — thiết kế, chứng minh, trade-off

### 6.1. Memory hiện có (trong code)

| Loại | Implementation | Phạm vi |
|------|----------------|--------|
| **Short-term (session)** | LangGraph `GlobalState` + Postgres checkpointer | 1 pipeline run |
| **Agent conversation** | `agent_messages`, `agent_logs` | 1 run |
| **Dedup decision cache** | `context_hash` + `DedupDecisionTrace` | 1 run, dedup retry |
| **Cross-run memory** | **Không có** | — |

### 6.2. Memory nên thiết kế (đề xuất cho báo cáo + implement)

**Mục đích (như bạn nêu):** Thêm context, giảm ảo giác — **trong phạm vi 1 pipeline hoặc cross-run cùng schema**.

**Cấu trúc đề xuất:**

```json
{
  "schema_hash": "sha256(columns+types+row_count_bucket)",
  "domain_hint": "healthcare | finance | ...",
  "successful_plans": [
    {
      "error_signature": {"dup_rate": 0.05, "null_cols": ["Address2"]},
      "execution_plan_snippet": { "...": "..." },
      "f1_achieved": 0.92,
      "timestamp": "..."
    }
  ],
  "failed_patterns": [
    {
      "task": "null_handling",
      "strategy": "fill_mean",
      "column": "PatientID",
      "reason": "identifier column"
    }
  ],
  "column_semantic_cache": {
    "DOB": {"semantic_type": "date", "confirmed": true}
  }
}
```

**Lưu trữ:** PostgreSQL table `agent_memory` hoặc Redis JSON keyed by `schema_hash`.

**Inject vào:** Planner prompt + Semantic Profiler (few-shot examples từ memory).

### 6.3. Kịch bản chứng minh memory (A/B test)

| | Run A (no memory) | Run B (with memory) |
|---|-------------------|---------------------|
| **Setup** | Hospital lần 1 — chạy cold | Hospital lần 2 — cùng schema, memory từ lần 1 |
| **Đo** | Planner tokens, replan count, F1 | Giảm tokens? Giảm replan? F1 ≥ lần 1? |
| **Kỳ vọng** | Baseline | Planner chọn strategy nhanh hơn; ít clarification hơn |

**Trường hợp memory KHÔNG tốt (ghi trong hạn chế):**
- Schema drift (thêm/xóa cột) → schema_hash miss → memory vô dụng
- Domain khác nhau cùng schema → strategy sai
- **Trade-off:** storage cost, stale memory, privacy (lưu plan có thể chứa sample data)

### 6.4. Mức implement cho đồ án

| Mức | Effort | Giá trị báo cáo |
|-----|--------|-----------------|
| **Minimal** | Document `context_hash` dedup như "in-run memory" | Trung bình |
| **Medium** | Schema-level plan cache (PostgreSQL) | Cao — có A/B test |
| **Full** | Cross-session mem0 / LangGraph Store | Rất cao — gần publish |

---

## 7. Use case metadata — bỏ Input Validator

### 7.1. Ý tưởng

> Khi dataset đã có metadata (schema, constraints, data dictionary) → skip Input Validator Q&A, inject thẳng vào Planner.

### 7.2. Hiện trạng code

- `InputValidatorAgent` prompt đã mention *"convert metadata cleaning rules"* khi user trả lời
- **Chưa có** endpoint / flag `metadata_mode` hoặc `skip_clarification`
- Ingestion trả metadata cơ bản (schema) nhưng chưa map → clarification answers

### 7.3. Thiết kế đề xuất

```
POST /pipeline/run
  + dirty_file
  + metadata_file (JSON/YAML)   ← NEW
  + pipeline_mode: "metadata"   ← NEW

Flow:
  profiler → semantic_profile → input_validator (SKIP if metadata complete)
    → planner (metadata as hard constraints)
```

**Metadata JSON schema gợi ý:**

```json
{
  "columns": {
    "PatientID": {"type": "identifier", "nullable": false, "unique": true},
    "DOB": {"type": "date", "format": "MM/DD/YYYY", "nullable": true, "fill": "leave_as_is"},
    "Phone": {"type": "phone", "nullable": true, "fill": "fill_mode"}
  },
  "dedup": {"keys": ["PatientID"], "keep": "first"},
  "skip_clarification": true
}
```

### 7.4. Eval cho báo cáo

| Mode | # câu HITL | Thời gian E2E | F1 |
|------|------------|---------------|-----|
| Interactive (no metadata) | ~5–15 | … | … |
| Metadata-first | 0 (Q&A) | ↓ | ≈ same nếu metadata đúng |

**Đóng góp claim:** *"Metadata-aware pipeline entry reduces HITL friction while preserving cleaning quality."*

---

## 8. Auto mode & benchmark scenarios

### 8.1. Đã có trong code

| Tính năng | File | Mô tả |
|-----------|------|-------|
| `pipeline_mode=benchmark` | `pipeline.py`, `graph.py` | Auto-resolver thay user |
| `resolve_benchmark_clarifications()` | `input_validator/resolver.py` | So dirty vs GT → trả lời Q&A |
| `MassUploadView` + auto-approve | `frontend/` | Batch benchmark |
| `benchmark_approved` flag | `input_validation.py` | Pause 1 lần cho user review answers |

### 8.2. Cần bổ sung / document

1. **Mode matrix** (ghi trong Ch.3/Ch.6):

| Mode | HITL Q&A | Plan approve | Result approve | GT cho planner |
|------|----------|--------------|----------------|----------------|
| interactive | User | User | User | Không |
| semi-auto | User | Auto | User | Không |
| benchmark | Auto-resolver | Auto | Auto | **Không** |
| metadata | Skip | User/Auto | User | Không |

2. **Before/After compare** (bạn yêu cầu):
   - UI đã có `ResultView` + F1
   - Thêm export: dirty vs cleaned vs GT diff table (10 rows sample)

3. **Auto-resolve transparency:**
   - Log `resolved_by_user` + `action_plans` trong benchmark → reviewer thấy resolver không "cheat" planner

---

## 9. Chọn model — cost vs quality

### 9.1. Lý thuyết chọn GPT-4o (hiện tại)

| Tiêu chí | GPT-4o | GPT-4o-mini | Llama 3.1 8B |
|----------|--------|---------------|--------------|
| Structured JSON output | Tốt | Khá | Trung bình |
| Semantic column typing | Tốt | Khá | Yếu hơn |
| Tool calling / ReAct | Tốt | Khá | Cần tune |
| Cost | Cao | ~10–20x rẻ hơn | Self-host |
| Latency | Trung bình | Nhanh hơn | Phụ thuộc GPU |

**Lý do chọn GPT-4o cho đồ án:** Planner + Semantic Profiler + Validator cần **structured output ổn định** — lỗi JSON = replan loop = cost tăng. AutoDCWorkflow paper cũng report model size ảnh hưởng workflow quality (Gemma 2-27B vs 9B).

### 9.2. Thí nghiệm ablation (bắt buộc cho mục 4 báo cáo)

**Chạy Hospital × 3 models × 3 lần:**

| Model | F1 | Token | Cost USD | Replan count | Plan valid % |
|-------|-----|-------|----------|--------------|--------------|
| gpt-4o | | | | | |
| gpt-4o-mini | | | | | |
| claude-sonnet (optional) | | | | | |

**Kết luận mẫu (nếu mini đủ tốt):**
> "gpt-4o-mini đạt 95% F1 của gpt-4o với 40% chi phí — đủ cho production; gpt-4o reserved cho semantic profiling phức tạp."

**Routing model theo node (cải tiến thực tế):**
- Semantic Profiler + Planner → gpt-4o
- Validator ReAct → gpt-4o-mini
- Workers → không LLM

---

## 10. Bảng đánh giá đóng góp (publish hay vận dụng?)

### 10.1. Đánh giá từng module

| Module | Loại | Có cải tiến? | Mức mới | Chứng minh cần | Publish potential |
|--------|------|--------------|---------|----------------|-------------------|
| Statistical Profiler (EDA) | Vận dụng | Thấp | ★☆☆ | So với pandas-profiling | Không |
| Semantic Profiler | Vận dụng Cocoon-like | Trung bình | ★★☆ | Semantic type accuracy | Thấp |
| Input Validator + Q&A | **Tích hợp mới** | Cao | ★★★ | HITL necessity study | Trung bình |
| Planner + skill file | Vận dụng + skill | Trung bình | ★★☆ | Plan validity rate | Thấp |
| Deterministic workers | Best practice | Thấp | ★☆☆ | Stability vs LLM code | Không |
| Hybrid Validator (Pandas+LLM) | **Có thể claim** | Cao | ★★★ | Ablation LLM-only vs hybrid | **Cao** |
| Retry/Replan loop | Vận dụng LangGraph | Trung bình | ★★☆ | Replan recovery rate | Trung bình |
| HITL 3 điểm + checkpointer | **Tích hợp mới** | Cao | ★★★ | UX + reliability metrics | Trung bình |
| Data Lineage (Postgres) | Vận dụng | Trung bình | ★★☆ | Version audit demo | Thấp |
| Benchmark auto-resolver | **Methodology** | Cao | ★★★ | No-GT-leak proof + F1 | **Cao** |
| Metadata-first mode | **Chưa có — đề xuất** | Cao nếu làm | ★★★ | A/B HITL reduction | Trung bình |
| Cross-run memory | **Chưa có — đề xuất** | Cao nếu làm | ★★★ | A/B test | **Cao** |

### 10.2. Trả lời câu hỏi "chỉ vận dụng thôi đúng không?"

**Không hoàn toàn.** Phân loại:

| Loại | % ước lượng | Ví dụ |
|------|-------------|-------|
| **Vận dụng thuần** | ~40% | LangGraph, FastAPI, Pandas workers, Parquet ingest |
| **Tích hợp/synthesis mới** | ~35% | End-to-end pipeline, HITL 3 điểm, benchmark mode, lineage |
| **Có thể claim khoa học** | ~25% | Hybrid validation, benchmark methodology, (memory/metadata nếu làm) |

### 10.3. Hướng publish paper (nếu muốn)

| Venue | Angle | Cần thêm |
|-------|-------|----------|
| Workshop (HILDA, ai4data) | HITL agentic data cleaning | Ch.6 đầy đủ + user study nhỏ |
| Short paper (EMNLP/ACL Findings adj.) | Benchmark methodology (no GT leak) | Hospital + Flights + ablation |
| Technical report / arXiv | Full system + open source | README + reproducibility |

**Không nên claim:** "First multi-agent data cleaning" — AutoDCWorkflow, Cocoon, Agentic-Cleanse đã có.

**Nên claim:** "Structured HITL multi-agent pipeline with hybrid validation and reproducible benchmark separation."

---

## 11. Roadmap ưu tiên (2–4 tuần)

### Tuần 1 — Thực nghiệm (P0)

- [ ] Chạy Hospital benchmark × 3 (S2) → điền F1
- [ ] Ablation model: gpt-4o vs gpt-4o-mini
- [ ] Per-component metrics (dedup/null/type riêng)
- [ ] Sửa Pandera + HITL inconsistency toàn báo cáo

### Tuần 2 — View 1 + View 2 (P1)

- [ ] Viết rõ 2 view trong Ch.6
- [ ] Scenario S1–S5
- [ ] So sánh baseline (naive pandas, one-shot LLM)
- [ ] Lấy F1 Cocoon/HoloClean từ paper cho Hospital → bảng so sánh

### Tuần 3 — Đóng góp (P1–P2)

- [ ] **Metadata-first mode** (UC-19) — implement minimal
- [ ] Document dedup `context_hash` như in-run memory
- [ ] (Optional) Schema-level plan cache + A/B test

### Tuần 4 — Báo cáo (P2)

- [ ] Bảng đóng góp mục 10 vào Ch.5
- [ ] Viết 5.7–5.12
- [ ] Case study + screenshot
- [ ] Checklist nộp (doc `huong_dan_chinh_sua_bao_cao_tot_nghiep.md`)

---

## Phụ lục: Trả lời nhanh các câu hỏi của bạn

| Câu hỏi | Trả lời ngắn |
|---------|--------------|
| Có ai làm MAS giống mình chưa? | **Có** — AutoDCWorkflow (3 agents), Cocoon (decomposed), Agentic-Cleanse (LangGraph). Bạn **khác** ở HITL 3 điểm + hybrid validation + lineage. |
| Chỉ vận dụng thôi? | **~40% vận dụng**, ~35% tích hợp, ~25% có thể claim nếu chứng minh. |
| Tại sao F1 tương đương/cao hơn? | Deterministic workers + validation loop; benchmark auto-resolver (ghi rõ điều kiện). |
| Hardcode benchmark? | **Không hardcode vào planner** — normalize ở evaluation layer; tách scenario. |
| Memory để làm gì? | Cache plan/strategy theo schema_hash; giảm replan + token. Cần A/B test. |
| Metadata skip validator? | **Chưa có** — implement `metadata_mode` là đóng góp rõ ràng. |
| Auto mode? | **Đã có** `benchmark_run` + MassUpload — cần document + before/after metrics. |

---

*Tài liệu liên quan:*
- `docs/huong_dan_chinh_sua_bao_cao_tot_nghiep.md` — checklist chỉnh sửa báo cáo
- `docs/F1-score script/.../benchmark_flow_implementation_plan.md` — nguyên tắc benchmark
- `docs/codebase_context_new.md` — architecture reference
