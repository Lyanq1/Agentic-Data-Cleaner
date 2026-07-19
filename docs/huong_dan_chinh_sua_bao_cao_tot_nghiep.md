# Hướng Dẫn Chỉnh Sửa Báo Cáo Đồ Án Tốt Nghiệp

> **Đề tài:** Ứng dụng AI Agents trong Kỹ thuật Xử lý Dữ liệu  
> **Hệ thống:** Agentic Data Cleaner (`Agentic-Data-Cleaner`)  
> **Ngày lập:** 07/2026  
> **Mục đích:** Tài liệu nội bộ hướng dẫn nhóm chỉnh sửa báo cáo trước khi nộp / bảo vệ, đối chiếu với codebase thực tế.

---

## Mục lục

1. [Tổng quan đánh giá](#1-tổng-quan-đánh-giá)
2. [Chương 3 — Phân tích hiện trạng](#2-chương-3--phân-tích-hiện-trạng)
3. [Chương 4 — Thiết kế hệ thống](#3-chương-4--thiết-kế-hệ-thống)
4. [Chương 4 & 5 — Triển khai](#4-chương-4--5--triển-khai)
5. [Chương 6 — Kết quả thực nghiệm (khung viết chi tiết)](#5-chương-6--kết-quả-thực-nghiệm-khung-viết-chi-tiết)
6. [Chương 7 — Kết luận & hạn chế](#6-chương-7--kết-luận--hạn-chế)
7. [Danh sách mâu thuẫn cần sửa gấp](#7-danh-sách-mâu-thuẫn-cần-sửa-gấp)
8. [Thứ tự ưu tiên công việc](#8-thứ-tự-ưu-tiên-công-việc)
9. [Phụ lục: Lệnh chạy thực nghiệm](#9-phụ-lục-lệnh-chạy-thực-nghiệm)

---

## 1. Tổng quan đánh giá

| Chương | Đánh giá | Vấn đề chính |
|--------|----------|--------------|
| **Ch.2** Cơ sở lý thuyết | Khá đầy đủ | Dài; có chỗ lệch so với code (Pandera) |
| **Ch.3** Phân tích hiện trạng | Trung bình | Thiên lý thuyết, thiếu khảo sát thực tế |
| **Ch.4** Thiết kế | Tốt về khung | Mâu thuẫn nội bộ HITL; thiếu Semantic Profiler |
| **Ch.5** Triển khai | Không đồng đều | Nhiều mục chỉ là tiêu đề (5.7–5.9) |
| **Ch.6** Thực nghiệm | **Yếu nhất** | Gần như placeholder, chưa có số liệu |
| **Ch.7** Kết luận | Viết sẵn | Một số claim chưa khớp code |

**Kết luận ngắn:** Báo cáo mạnh ở lý thuyết và thiết kế kiến trúc, nhưng **yếu ở hiện trạng thực tế** và **rất yếu ở thực nghiệm**. Hội đồng thường chấm nặng Ch.3 (bài toán có thật không?) và Ch.6 (có số liệu không?).

---

## 2. Chương 3 — Phân tích hiện trạng

### 2.1. Điểm đang ổn (giữ lại)

- **3.1.1** Mô tả quy trình làm sạch thủ công (profiling → xác định lỗi → viết script → kiểm tra → lặp) hợp lý, có số liệu CrowdFlower/Appen (60% thời gian cho cleaning).
- **3.1.3** Bảng so sánh OpenRefine, Trifacta, GE/Pandera, LLM chat, AutoClean và **gap analysis** 5 điểm là phần mạnh nhất của chương.
- **3.2** Mô tả use case chi tiết, khớp API thực tế (`/pipeline/run`, `/resolve`, `/approve_plan`, `/benchmark_run`, WebSocket).

### 2.2. Điểm chưa ổn (cần sửa)

#### a) Thiếu “hiện trạng” thực tế — quá giáo trình

`3.1.1` và `3.1.2` đang là mô tả chung của ngành, chưa có:

- Khảo sát thực tế (phỏng vấn KTV dữ liệu, case study, hoặc mô phỏng có số liệu)
- Bối cảnh cụ thể: ai là người dùng, tần suất làm sạch, loại file thường gặp
- Pain point định lượng: thời gian/dataset, tỷ lệ lỗi hay gặp, chi phí rework

#### b) Gap analysis gắn sai công nghệ

Mục `3.1.3` ghi đóng góp là *“engine validation Pandera”*, nhưng code thực tế dùng **Custom Pandas Validator** (`app/tools/data/quality_control/validator.py`), **không** dùng thư viện Pandera.

#### c) Lỗi đếm use case

Đoạn mở đầu `3.2` nói **16 UC**, nhưng thực tế có **UC-01 → UC-18** (18 use case). Cần thống nhất.

#### d) Chưa giải thích “tại sao cần Multi-Agent”

Báo cáo liệt kê gap nhưng chưa lập luận rõ: vì sao một LLM đơn (CleanAgent, Cocoon) chưa đủ, mà cần tách Profiler / Validator / Planner / Workers. Đây là câu hỏi hội đồng hay đặt ra.

### 2.3. Nội dung đề xuất bổ sung

#### Mục mới: **3.1.4 Khảo sát / phân tích bài toán cụ thể**

Thêm bảng pain point (điền số liệu thực tế sau khi khảo sát hoặc mô phỏng):

| Loại lỗi | Tần suất gặp (%) | Xử lý thủ công hiện tại | Thời gian ước tính |
|----------|------------------|--------------------------|---------------------|
| Duplicate | … | GROUP BY / drop_duplicates thủ công | … phút |
| Null / DMV | … | fillna ad-hoc, quyết định theo kinh nghiệm | … phút |
| Type mismatch | … | astype + kiểm tra lại từng cột | … phút |

#### Mục mới: **3.1.5 Lý do chọn kiến trúc Multi-Agent**

Gợi ý nội dung (3–5 đoạn):

1. **Phân tách trách nhiệm:** Profiler (thống kê) vs Semantic Profiler (ngữ nghĩa) vs Planner (chiến lược) vs Workers (thực thi deterministic).
2. **Kiểm soát chất lượng:** Validator chạy sau mỗi worker, không để lỗi lan truyền.
3. **HITL có cấu trúc:** Con người can thiệp tại điểm quyết định, không phải viết lại toàn bộ pipeline.
4. **So sánh ngắn với single-agent:** CleanAgent/Cocoon mạnh ở profiling + cleaning nhưng thiếu orchestration, retry/replan, lineage — đề tài bổ sung các lớp này.

#### Sửa gap analysis (mục 3.1.3, điểm 4)

**Trước:**
> Kiểm soát chất lượng tự động bằng engine validation chuyên dụng (Pandera) với cơ chế retry/replan.

**Sau (khớp code):**
> Kiểm soát chất lượng tự động bằng **Custom Pandas Validation Engine** kết hợp **LLM Validator (ReAct)**, với cơ chế retry/replan tối đa 3 lần mỗi task.

---

## 3. Chương 4 — Thiết kế hệ thống

### 3.1. Điểm mạnh (giữ nguyên)

- Kiến trúc LangGraph 9 node, `GlobalState`, 3 hàm routing, lineage PostgreSQL — khớp codebase.
- Thiết kế worker (dedup hybrid, null deterministic, type cast) mô tả đúng hướng triển khai.
- Frontend (breadcrumb, polling, WebSocket, HITL panels) khớp `frontend/`.

### 3.2. Điểm cần sửa

#### a) Thiếu mục thiết kế Semantic Profiler Agent

Trong `4.4`, sau `4.4.1 Profiler Node (EDA)` nhảy thẳng sang `4.4.2 Input Validator`, trong khi pipeline có node `semantic_profile` / `SemanticProfilerAgent` — đây là **đóng góp LLM quan trọng** của đề tài.

**Đề xuất:** Thêm **4.4.2 Semantic Profiler Agent**, đánh lại số thứ tự các mục sau (Input Validator → 4.4.3, Planner → 4.4.4, …).

Nội dung tối thiểu cho mục mới:

| Thành phần | Mô tả |
|------------|-------|
| Input | `StatisticalProfile` + top popular rows từ dataset |
| Xử lý | LLM `structured_output` → `SemanticProfile` per column |
| Output | `semantic_data_type`, `fill_strategies`, `is_error`, `error_types` |
| Vai trò | Cung cấp ngữ cảnh nghiệp vụ cho Input Validator và Planner |

#### b) Mâu thuẫn về HITL — cần thống nhất toàn báo cáo

| Vị trí trong báo cáo | Nội dung |
|----------------------|----------|
| Bảng 2.4 | HITL-1 = duyệt kế hoạch; HITL-2 = duyệt kết quả |
| Mục 4.5.2 | Gọi “làm rõ đầu vào” là HITL-1, “duyệt kế hoạch” là HITL-2 |
| Đoạn 4.5.2 (sau duyệt kế hoạch) | *“resume pipeline không còn điểm dừng nào khác”* |
| Mục 3.3.5 / 6.5.3 | Có Checkpoint 2: phê duyệt kết quả trước `report_agent` |

**Phiên bản đúng (khớp code `app/graphs/graph.py`):**

```
interrupt_before = ["deduplication", "null_handling", "type_casting", "report_agent"]
```

| Điểm | Vị trí | Mô hình | Mục đích |
|------|--------|---------|----------|
| Làm rõ đầu vào (Q&A) | Sau `input_validator` | Feedback-based | Làm rõ null/dedup/typecast khi prompt không đủ |
| Checkpoint 1 | Trước workers (`deduplication`, …) | Approval-based | Duyệt Execution Plan |
| Checkpoint 2 | Trước `report_agent` | Approval-based | Duyệt kết quả làm sạch trước khi xuất báo cáo |

**Hành động:** Xóa câu “không còn điểm dừng nào khác” ở mục 4.5.2. Thống nhất đánh số HITL trên tất cả chương.

#### c) Pandera — sửa toàn báo cáo

Pandera xuất hiện ở Ch.2, 3, 4, 7 và frontend (`pandera_checks`). Thực tế:

- Validator tầng 1: `validate_dataframe()` — Pandas thuần
- Validator tầng 2: `ValidatorAgent` — ReAct + `perform_data_quality_check`
- **Không** import hay dùng thư viện `pandera`

**Thay thế nhất quán:** “Custom Pandas Validation Engine” hoặc “Pandas-based rule engine”.

#### d) Report Agent

Bảng 4.2 ghi `ReportAgent` dùng LLM, nhưng `report_agent_node` chủ yếu:

- Tính F1 (cell-level error correction) khi có ground truth
- Tổng hợp `token_metrics`
- **Không** gọi `ReporterAgent` (có prompts nhưng chưa wire vào graph)

**Ghi đúng:** “Report node: tổng hợp metrics deterministic; LLM reporter là hướng phát triển.”

#### e) Workflow UI

- Ch.7: workflow **3 bước** (Upload → Pipeline → Result)
- Ch.4.9: breadcrumb **4 bước** (Upload → Statistical Profile → Pipeline → Results)

**Chọn một:** Khuyến nghị dùng **4 bước** vì khớp `Header.tsx` / `pipelineSession.ts`.

---

## 4. Chương 4 & 5 — Triển khai

### 4.1. Phần viết tốt (tham khảo mẫu cho các mục còn thiếu)

- `5.5.1` Deduplication, `5.5.2` Null, `5.5.3` Type Casting, `5.6.1` Validator
- Có input/output, class/hàm, config (`gpt-4o`, `max_retries=3`)
- Ghi nhận trung thực: `failure_policy` *“chưa được validator_node đọc”* — giữ và đưa vào hạn chế Ch.7

### 4.2. Phần chưa ổn

| Mục | Vấn đề |
|-----|--------|
| `5.7` Lineage + Checkpointer | Chỉ có tiêu đề |
| `5.8` LangGraph StateGraph | Chỉ có tiêu đề |
| `5.9` API + Frontend | Chỉ có tiêu đề |
| `5.3.2`–`5.4.2` | Quá mỏng so với độ phức tạp code |
| Toàn Ch.5 | Lặp Ch.4 nhiều; thiếu snippet code và trade-off |

### 4.3. Cấu trúc đề xuất lại Chương 5

```
5.1  Môi trường & cấu hình (giữ)
5.2  Data Ingestion & Parquet canonical (giữ)
5.3  Agent Registry & LLM Factory
5.4  Profiler & Semantic Profiler (tách rõ, thêm code)
5.5  Input Validator & Planner (thêm skill data-cleaning-planner)
5.6  Workers: Dedup / Null / TypeCast (giữ, bổ sung snippet)
5.7  Validator hybrid + Retry/Replan (giữ 5.6.x)
5.8  Lineage Service + PostgreSQL Checkpointer  ← VIẾT MỚI
5.9  LangGraph: build_graph, routing, interrupt_before  ← VIẾT MỚI
5.10 FastAPI endpoints + WebSocket streaming      ← VIẾT MỚI
5.11 React Frontend & HITL panels                 ← VIẾT MỚI
5.12 Benchmark mode & auto-resolver               ← VIẾT MỚI
```

### 4.4. Gợi ý nội dung cho 5.8 (Lineage)

- ORM: `Session`, `LineageVersion`, `DatasetRecord` (`app/models/lineage.py`)
- `LineageService.append_new_version_from_file()` — gọi sau validator pass
- Mỗi worker pass → 1 phiên bản Parquet mới trên PostgreSQL JSONB

### 4.5. Gợi ý nội dung cho 5.9 (LangGraph)

- `GraphBuilder.build()`: 9 node, 3 conditional edges
- `route_from_input_validator`, `route_to_current_task`, `route_from_validator`
- `interrupt_before` mặc định; resume sau approve bỏ interrupt

### 4.6. Gợi ý nội dung cho 5.10–5.11 (API + FE)

| Endpoint | Chức năng |
|----------|-----------|
| `POST /api/v1/pipeline/run` | Upload + khởi chạy |
| `POST .../resolve` | Trả lời clarification |
| `POST .../approve_plan` | Duyệt kế hoạch |
| `GET .../state` | Polling trạng thái |
| `GET .../download` | Tải kết quả |
| `POST .../benchmark_run` | Benchmark + ground truth |
| `WS /ws/{run_id}` | Log realtime |

Frontend: `PipelineView`, `HITLCheckpointPanel`, `ExecutionPlanPanel`, `MassUploadView`.

---

## 5. Chương 6 — Kết quả thực nghiệm (khung viết chi tiết)

> **Trạng thái hiện tại:** Bảng 6.1 trống; 6.2.1–6.2.3 ghi “Trình bày báo cáo”; 6.3.2–6.7 hầu hết chỉ tiêu đề.  
> **Nguyên tắc:** Chỉ đưa dataset và số liệu đã chạy thật.

### 5.1. Bộ dữ liệu thử nghiệm (6.1)

#### Tier 1 — Có sẵn trong repo (chạy ngay)

| STT | Dataset | File | Ground truth | Ghi chú |
|-----|---------|------|--------------|---------|
| 1 | Hospital | `tests/hospital-dirty.csv` | `tests/hospital_clean.csv` | Benchmark chính |
| 2 | Hospital variant | `tests/hospital-1.csv` | `tests/hospital-1-new.csv` | Bổ sung |
| 3 | Olist Products | `tests/olist_products_dataset.csv` | Không có | Chỉ test profiling |

#### Tier 2 — Liệt kê trong báo cáo (Beer, Flight, Rayyan, Movie, Tax)

**Chỉ giữ trong bảng 6.1 nếu đã tải GT và chạy benchmark.** Nếu chưa → xóa hoặc chuyển sang “hướng phát triển” (Ch.7).

#### Mẫu Bảng 6.1 (điền sau khi đếm)

| STT | Tập dữ liệu | Miền | Số dòng (bẩn) | Số cột | Lỗi chính |
|-----|-------------|------|---------------|--------|-----------|
| 1 | Hospital | Y tế | *điền* | *điền* | dup, null, type |
| … | … | … | … | … | … |

### 5.2. Kịch bản thử nghiệm (6.2)

Thay 3 dòng “Tự động hoàn toàn / Trình bày báo cáo” bằng:

| Kịch bản | Mô tả | API / Công cụ | Mục đích đo |
|----------|-------|---------------|-------------|
| **S1 — Interactive + HITL** | User upload, trả lời clarification, duyệt plan, duyệt kết quả | `POST /pipeline/run` | UX, thời gian E2E, số câu HITL |
| **S2 — Benchmark tự động** | Dirty + GT; auto-resolver trả lời thay user | `POST /pipeline/benchmark_run` | F1, precision, recall |
| **S3 — Batch benchmark** | Nhiều file, concurrency, auto-approve | `MassUploadView` (`/massupload`) | Throughput, ổn định, token |

#### Nguyên tắc benchmark (bắt buộc ghi trong 6.2)

Theo `docs/F1-score script/.../benchmark_flow_implementation_plan.md`:

1. **Planner và workers KHÔNG đọc ground truth** trực tiếp.
2. Ground truth chỉ dùng cho: (a) auto-resolver trả lời clarification, (b) tính F1 ở `report_agent`.
3. Lý do: nếu planner đọc GT → F1 ~100% giả tạo, không đo năng lực thật.

### 5.3. Đánh giá chất lượng làm sạch (6.3)

#### 6.3.1 — Metrics (giữ, bổ sung định nghĩa khớp code)

| Metric | Định nghĩa | Có trong code? |
|--------|------------|----------------|
| **Cell Accuracy** | Ô khớp GT / tổng ô | Có (`cell_accuracy`) |
| **Error Correction Precision** | TP / (TP + FP) — ô sửa đúng trong số ô đã đổi | Có |
| **Error Correction Recall** | TP / (TP + FN) — ô sửa đúng trong số ô bẩn thật | Có |
| **F1-Score** | Harmonic mean P & R | Có |
| **Null Reduction Rate (NRR)** | (null_gốc − null_sau) / null_gốc × 100% | **Chưa** — tự tính hoặc bỏ |
| **Duplicate Removal Accuracy** | So sánh tập dòng bị xóa vs GT | **Chưa** — tự tính hoặc bỏ |

**Định nghĩa TP/FP/FN (cell-level, khớp `report_agent_node`):**

- **TP:** Ô sai ở dirty, đã sửa đúng theo GT
- **FP:** Ô bị đổi nhưng không khớp GT (sửa sai)
- **FN:** Ô sai ở dirty, chưa sửa đúng theo GT

#### Mẫu Bảng 6.2 — F1 theo dataset (S2, n ≥ 3 lần chạy)

| Dataset | Cell Acc. | Precision | Recall | F1 | Thời gian (s) | Token |
|---------|-----------|-----------|--------|-----|---------------|-------|
| Hospital (lần 1) | | | | | | |
| Hospital (lần 2) | | | | | | |
| Hospital (lần 3) | | | | | | |
| **Trung bình** | | | | | | |

#### Mẫu Bảng 6.3 — Phân rã theo loại lỗi (6.3.3)

| Loại lỗi | Số ô bẩn (GT≠dirty) | TP | FP | FN | Recall |
|----------|---------------------|----|----|-----|--------|
| Duplicate (ảnh hưởng hàng) | | | | | |
| Null / DMV | | | | | |
| Type cast | | | | | |

*Ghi chú phương pháp: lọc cột/cell theo loại lỗi dominant trong GT diff.*

#### 6.3.2 — So sánh baseline

| Phương pháp | F1 | Thời gian (s) | Ghi chú |
|-------------|-----|---------------|---------|
| **Hệ thống đề tài (S2)** | | | Multi-agent + validation |
| Pandas script thủ công (theo GT) | | | Upper bound gần |
| `drop_duplicates` + `fillna` mặc định | | | Baseline naive |
| Single LLM (1-shot prompt → code) | | | ChatGPT/Claude viết script 1 lần |

**Tham chiếu học thuật:** ELT-Bench (SRDEL, SRDT, cost, steps) — map sang đề tài:

| ELT-Bench | Đề tài |
|-----------|--------|
| SRDEL (extract/load success) | Tỷ lệ pipeline chạy hết không lỗi |
| SRDT (transformation success) | Tỷ lệ đạt F1 ≥ ngưỡng (vd. 0.85) |
| Average cost (tokens) | `token_metrics` tổng |
| Average steps | Số node + số retry |

### 5.4. Hiệu năng & truy vết (6.4)

#### Bảng 6.4 — Thời gian từng giai đoạn (Hospital, S2)

| Giai đoạn | Thời gian TB (s) | % tổng |
|-----------|------------------|--------|
| Ingest + Profiler (EDA) | | |
| Semantic Profile (LLM) | | |
| Input Validator | | |
| Planner (LLM) | | |
| Deduplication | | |
| Null Handling | | |
| Type Casting | | |
| Validator (×3 vòng) | | |
| Report | | |
| **Tổng** | | 100% |

*Nguồn: timestamp trong `agent_logs`, WebSocket, hoặc LangSmith.*

#### 6.4.2 — Data Lineage

- Số phiên bản `LineageVersion` sau mỗi worker pass
- Ví dụ: v1 (ingest) → v2 (dedup) → v3 (null) → v4 (typecast)

#### 6.4.3 — Phản hồi realtime

- WebSocket latency (log xuất hiện trên FE < X giây sau node complete)
- Polling interval: 3s running, 1s resolving_hitl

### 5.5. Đánh giá HITL (6.5)

| Checkpoint | Tỷ lệ run cần can thiệp | Số câu hỏi TB | Thời gian user (s) |
|------------|-------------------------|---------------|---------------------|
| Clarification Q&A | / | | |
| Plan approval | / | — | |
| Result approval | / | — | |

**Case study:** 1 run Hospital (S1) kèm screenshot `HITLCheckpointPanel`, `ExecutionPlanPanel`.

### 5.6. Chi phí API (6.6)

| Node / Agent | Prompt tokens | Completion tokens | Chi phí USD (gpt-4o) |
|--------------|---------------|-------------------|------------------------|
| semantic_profile | | | |
| input_validator | | | |
| planner | | | |
| deduplication | | | |
| validator (LLM) | | | |
| **Tổng** | | | |

*Nguồn: `state.token_metrics`, `TokenTrackerCallback`.*

### 5.7. Thảo luận (6.7)

#### 6.7.1 Ưu điểm (cần bằng chứng số)

- Hybrid LLM (suy luận) + Pandas (thực thi) → F1 cao hơn baseline naive
- Retry/replan giảm tỷ lệ fail cứng
- Lineage + HITL tăng tin cậy và khả năng audit

#### 6.7.2 Hạn chế (trung thực, khớp code)

| Hạn chế | Chi tiết |
|---------|----------|
| Fuzzy dedup | `run_fuzzy_blocking` chỉ preview, chưa auto-merge |
| `fill_llm` | Chưa implement; null agent bỏ qua strategy này |
| Unit test | `tests/unit/` chưa có |
| Dataset benchmark | Mới có Hospital đầy đủ GT trong repo |
| ReporterAgent | Chưa wire LLM vào graph |

#### 6.7.3 Bài học kinh nghiệm (gợi ý)

- Prompt planner nên tách skill file (`data-cleaning-planner/SKILL.md`) để dễ debug
- Deterministic workers giúp reproducibility khi demo/benchmark
- Benchmark mode cần tách GT khỏi planner để số liệu có ý nghĩa

---

## 6. Chương 7 — Kết luận & hạn chế

### Sửa các claim sai

| Mục | Sai | Đúng |
|-----|-----|------|
| 7.1.3 | “Kiểm định bằng Pandera, lazy=True” | Custom Pandas Validator + LLM ReAct |
| 7.1.4 / 7.2.1 | “Chưa hỗ trợ batch nhiều tệp” | Đã có `MassUploadView` — ghi là batch queue có giới hạn concurrency |
| 7.1.1 | Workflow 3 bước | 4 bước (có Statistical Profile) |
| 7.2.2 | Fuzzy chưa hoàn chỉnh | Đúng — giữ, mô tả preview-only |

---

## 7. Danh sách mâu thuẫn cần sửa gấp

| # | Vấn đề | Vị trí | Hành động |
|---|--------|--------|-----------|
| 1 | Pandera vs Custom Pandas Validator | Ch.2, 3, 4, 7, FE | Sửa toàn bộ |
| 2 | HITL numbering + “không còn điểm dừng” | 4.5.2, Bảng 2.4 | Thống nhất 3 điểm |
| 3 | 16 vs 18 use case | 3.2 mở đầu | Sửa thành 18 |
| 4 | Bảng 6.1 trống | Ch.6 | Điền số hoặc bỏ dataset |
| 5 | 6.2 placeholder | Ch.6 | Thay bằng S1/S2/S3 |
| 6 | Report Agent = LLM | Bảng 4.2, 7.1 | Ghi deterministic F1 |
| 7 | Thiếu Semantic Profiler trong 4.4 | Ch.4 | Thêm mục 4.4.2 |
| 8 | 5.7–5.9 trống | Ch.5 | Viết nội dung hoặc gộp mục |
| 9 | `pandera_checks` trong FE | `ExecutionPlanPanel.tsx` | Đổi label cho khớp báo cáo |

---

## 8. Thứ tự ưu tiên công việc

| Ưu tiên | Việc | Ước lượng |
|---------|------|-----------|
| **P0** | Chạy benchmark Hospital ≥3 lần, điền Bảng 6.2 | 2–4 giờ |
| **P0** | Sửa Pandera + HITL trên toàn báo cáo | 2–3 giờ |
| **P1** | Viết đầy đủ 6.2–6.7 theo khung mục 5 | 1–2 ngày |
| **P1** | Bổ sung 3.1.4 + 3.1.5 | 0.5 ngày |
| **P2** | Hoàn thiện 5.8–5.12 | 1 ngày |
| **P2** | Thêm 4.4.2 Semantic Profiler | 0.5 ngày |
| **P3** | Sửa label FE `pandera_checks` | 30 phút |

---

## 9. Phụ lục: Lệnh chạy thực nghiệm

### 9.1. Khởi động hệ thống

```bash
cd /path/to/Agentic-Data-Cleaner
make setup
make run
# Terminal khác:
cd frontend && npm install && npm run dev
```

### 9.2. Benchmark đơn lẻ (có F1)

```bash
python scripts/run_pipeline_test.py \
  --dirty tests/hospital-dirty.csv \
  --ground-truth tests/hospital_clean.csv \
  --auto-approve
```

### 9.3. Benchmark qua API

```bash
curl -X POST "http://localhost:8000/api/v1/pipeline/benchmark_run" \
  -F "dirty_file=@tests/hospital-dirty.csv" \
  -F "clean_file=@tests/hospital_clean.csv"
```

### 9.4. Batch benchmark

1. Mở `http://localhost:5173/massupload`
2. Thêm nhiều dòng: dirty + clean file
3. Bật **Auto-approve HITL**
4. Set concurrency = 2
5. Export kết quả F1 từng file

### 9.5. Thu thập số liệu cho bảng

| Số liệu | Nguồn |
|---------|-------|
| F1, precision, recall | Response `f1_metrics` / `ResultView` |
| Token | `token_metrics` trong state / report |
| Thời gian từng node | `agent_logs` / WebSocket / LangSmith |
| Lineage versions | PostgreSQL `lineage_versions` |
| Số câu HITL | `input_validation_result.clarifications` |

---

## Checklist trước khi nộp báo cáo

- [ ] Không còn từ “Pandera” nếu code không dùng Pandera
- [ ] Bảng 6.1–6.4 có số thật, không để ô trống
- [ ] Không còn cụm “Trình bày báo cáo” trong Ch.6
- [ ] HITL thống nhất 3 điểm trên mọi chương
- [ ] 18 use case (không ghi 16)
- [ ] Semantic Profiler có mục thiết kế riêng
- [ ] Ch.7 hạn chế khớp code (batch, fuzzy, fill_llm)
- [ ] Có ít nhất 1 case study + screenshot HITL
- [ ] Đã nêu nguyên tắc benchmark (planner không đọc GT)

---

*Tài liệu tham chiếu codebase: `docs/codebase_context_new.md`, `docs/F1-score script/.../benchmark_flow_implementation_plan.md`*
