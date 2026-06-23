# Implementation Plan: Benchmark Flow (Dirty Dataset → Ground Truth)

## 1. Mục tiêu

Thêm một luồng phụ (benchmark flow) chạy song song với flow chính (interactive flow), dùng để đo năng lực hệ thống tự làm sạch một dataset dơ sao cho khớp với một file ground truth cho trước, thông qua F1-score ở `report_agent`.

**Nguyên tắc bất biến:** flow chính (có user, có `input_validator` hỏi đáp qua FE) không bị thay đổi hành vi. Mọi thay đổi phải an toàn khi `pipeline_mode` không được set (`None` → coi như `"interactive"`).

**Nguyên tắc benchmark đã chốt (tham khảo Cocoon, AutoDCWorkflow):** Planner và các worker **không được đọc trực tiếp** nội dung file ground truth. Ground truth chỉ giữ 2 vai trò:
1. Trả lời thay người dùng tại đúng các câu hỏi mà `input_validator` tự đặt ra (thay thế HIL, không phải cấp đáp án trước).
2. Thước đo F1-score ở `report_agent`, sau khi pipeline đã chạy xong.

Lý do: nếu planner đọc thẳng ground truth, hệ thống sẽ luôn đạt F1 ~100%, không còn đo được năng lực thật — đúng như rủi ro đã phân tích và được xác nhận qua cách Cocoon/AutoDCWorkflow thiết kế benchmark của họ.

---

## 2. Kiến trúc tổng quan

```
normalizer → profiler → semantic_profile → input_validator → planner → workers → report_agent
                                                  ↑
                                    [benchmark mode: auto-resolver
                                     trả lời thay người dùng]
```

`input_validator` **không bị bypass**. Nó vẫn chạy ở cả 2 mode, vẫn phát hiện vấn đề và đặt câu hỏi như cũ. Khác biệt duy nhất nằm ở **ai trả lời câu hỏi đó**:
- Interactive mode: người dùng trả lời qua FE.
- Benchmark mode: một auto-resolver tra `ground_truth_path` để trả lời tự động, theo đúng format câu trả lời người dùng.

Planner nhận input giống nhau về *cấu trúc* ở cả 2 mode — chỉ khác nguồn gốc của các câu trả lời trong `input_validation_result`.

---

## 3. Thay đổi cụ thể theo file

### 3.1 `app/graphs/states/global_state.py`
Thêm 2 field mới, không sửa field cũ:
```python
pipeline_mode: Literal["interactive", "benchmark"] | None
ground_truth_path: str | None
```
- Default `None` → tương đương `"interactive"`, không ảnh hưởng run hiện tại.

### 3.2 `app/agents/input_validator/` (hoặc nơi tương đương)
Thêm một **auto-resolver** mới, tách biệt khỏi logic phát hiện vấn đề hiện tại:
- Input: câu hỏi/clarification mà `input_validator` định gửi lên FE + `ground_truth_path`.
- Logic: so dirty dataset với ground truth tại đúng phạm vi câu hỏi (ví dụ: cột nào cần chuẩn hoá, chọn primary key nào, fill strategy nào cho cột nào) để suy ra câu trả lời.
- Output: trả về đúng format mà câu trả lời người dùng thật sẽ có, ghi vào `input_validation_result.clarifications` như cũ.

Điều kiện gọi auto-resolver: `state.get("pipeline_mode") == "benchmark"`. Khi đó, node **không** dừng lại chờ FE (bỏ qua nhánh interrupt/HITL), mà tự gọi resolver rồi tiếp tục chạy trong cùng 1 lượt.

Logic phát hiện vấn đề từ Statistical Profiler + Semantic Profiler bên trong `input_validator` giữ nguyên 100% — dùng chung cho cả 2 mode.

### 3.3 `app/graphs/edges.py`
**Không cần thêm conditional edge bypass** (đã loại bỏ hướng này). Cạnh `semantic_profile → input_validator` giữ nguyên tĩnh như flow chính.

Cạnh `input_validator → planner` (`route_from_input_validator`) giữ nguyên — vì benchmark mode giờ cũng luôn kết thúc `input_validator` ở trạng thái "ready" (đã có câu trả lời tự động), nên route đi tới `planner` tự nhiên như flow chính, không cần nhánh rẽ riêng.

### 3.4 `app/agents/planner/agent.py`
Theo `planner_input_summary.md`, planner chỉ ghép `input_validation_result` dưới dạng text block vào prompt (không structured-parse field lồng nhau trong code) → sửa nhẹ tại điểm build Human Message:

```python
pipeline_mode = state.get("pipeline_mode", "interactive")

if pipeline_mode == "benchmark":
    user_instruction_block = (
        "User Instruction: N/A — no user requirement; goal is the cleanest "
        "possible version of this dataset."
    )
else:
    user_instruction_block = f"User Instruction: {state.get('user_prompt')}"

# input_validation_result luôn có giá trị hợp lệ ở cả 2 mode (đã qua auto-resolver
# trong benchmark mode), nên không cần branch riêng cho phần Input Validation Decision.
decision_block = f"Input Validation Decision: {state.get('input_validation_result')}"
```

Không cần thêm field `cleaning_context` / `user_decisions` trung gian (đã loại bỏ hướng tách field — không cần thiết vì planner chỉ làm prompt injection, không structured access).

**Không đọc `ground_truth_path` ở planner.** Đây là ràng buộc cứng theo nguyên tắc ở mục 1.

### 3.5 `app/agents/report_agent/` (đã có sẵn theo flow chính)
Không đổi logic F1-score hiện tại — nó đã nhận `ground_truth_path` (tuỳ chọn) để so với `physical_dataframe_path` cuối cùng, dùng chung cho cả 2 mode, đúng như hệ thống đang vận hành.

### 3.6 API layer
Thêm 1 entrypoint mới (ví dụ `/api/v1/pipeline/benchmark_run`):
- Nhận 2 file: dirty dataset + ground truth.
- Set `initial_state["pipeline_mode"] = "benchmark"`, `initial_state["ground_truth_path"] = <path ground truth>`.
- Không set `user_prompt` (hoặc set rõ là rỗng/None).
- Gọi `ainvoke` trên **graph hiện có**, không compile graph riêng.

Endpoint cũ (`/api/v1/pipeline/run`) không đổi.

---

## 4. Việc cần làm trước khi code thật

- [ ] Xác nhận format cụ thể của `input_validation_result.clarifications` (cấu trúc Pydantic model) để auto-resolver trả về đúng shape.
- [ ] Liệt kê toàn bộ loại câu hỏi mà `input_validator` có thể đặt ra (dedup primary key, null fill strategy, type cast ambiguity, allow_missing override...) → viết resolver cho từng loại.
- [ ] Xác nhận schema ground truth khớp 1-1 với dirty dataset (cùng số cột, cùng tên cột) — nếu không khớp, auto-resolver cần thêm bước align schema trước khi so sánh.
- [ ] Rà lại system prompt / `SKILL.md` của planner (`data-cleaning-planner/SKILL.md`) xem có đoạn nào hard-code giả định luôn có `user_prompt` thật không.

## 5. Rủi ro tồn đọng

| Rủi ro | Mức độ | Ghi chú |
|---|---|---|
| Auto-resolver suy luận sai câu trả lời (vì so sánh dirty vs ground truth không trivial với mọi loại lỗi) | Trung bình | Cần test với nhiều loại lỗi khác nhau trước khi tin tưởng F1 đo đúng |
| `input_validator` có nhánh code giả định luôn có FE để interrupt/chờ | Trung bình | Cần kiểm tra cơ chế HITL hiện tại (LangGraph interrupt) có cho phép tự động resume bằng resolver hay cần sửa thêm |
| Ground truth file không cùng cấu trúc cột với dirty dataset | Thấp–Trung bình | Tùy dataset benchmark cụ thể |
