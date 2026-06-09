# Phân tích Luồng Log và State Management hiện tại

Dựa trên việc đọc mã nguồn trong hai thư mục `app` và `frontend`, dưới đây là báo cáo phân tích về cách hệ thống đang xử lý log, cập nhật trạng thái (state) và cơ chế retry của các agents.

## 1. Cơ chế hiển thị Log trên Frontend hiện tại
**Tình trạng:** Frontend không nhận được log thực tế của agent mà chỉ tự tạo ra các log "giả lập" (synthetic logs) dựa trên trạng thái của luồng (pipeline state).

- **Nơi xử lý:** `frontend/src/api/services.ts` (hàm `getFullState`)
- **Cách hoạt động:** 
  - Frontend gọi API `GET /pipeline/{runId}/state` để lấy `GlobalState` của LangGraph.
  - Tại file `services.ts`, hàm `getFullState` tự động ánh xạ các bước trong `data.completed_steps` và `data.current_step` thành mảng `agent_logs`. 
  - Ví dụ: Khi thấy `current_step === 'profiling'`, frontend tự "hardcode" một câu log: *"Running detailed statistical exploratory data analysis (EDA)..."*.
- **Vấn đề:** Điều này giải thích tại sao người dùng chỉ thấy các message tĩnh và thỉnh thoảng thấy việc "get state" (vì polling). Frontend hoàn toàn "mù" về việc agent bên trong thực sự đang suy nghĩ gì, gọi tool nào hay lỗi/retry ra sao.

## 2. Cơ chế Log và Agent Execution trên Backend
**Tình trạng:** Backend dùng logging tiêu chuẩn in ra terminal, không lưu log chi tiết vào State để trả cho Frontend.

- **Nơi xử lý:** `app/graphs/nodes.py`, `app/agents/base.py`, và các agents.
- **Cách hoạt động:**
  - Các node (ví dụ: `planner_node`, `supervisor_node`, `validator_node`) và các worker (ví dụ: `dedup_agent_node`) đang dùng `logger.info(...)` để in ra terminal console.
  - State của hệ thống (`GlobalState` trong `app/graphs/states/global_state.py`) có lưu `current_step`, `completed_steps`, `worker_states`, `validation_results` và `global_errors`, nhưng **không có field nào lưu trữ dòng thời gian (timeline) log chi tiết của từng agent**.
- **Vấn đề:** Do không lưu vào state, mọi hành động suy nghĩ (thinking process), gọi tool, hay lỗi nội bộ của LLM chỉ có dev đọc terminal mới thấy được.

## 3. Bản chất của việc "Retry" mà người dùng thấy ở Terminal
**Tình trạng:** Việc "retry" đang diễn ra không phải là vòng lặp retry ở cấp độ Graph (Planner/Supervisor), mà là retry ngầm ở cấp độ LLM (của LangChain/LangGraph).

- **Cấp độ Graph (Chưa kích hoạt retry thực sự):** Trong `app/graphs/nodes.py`, node `validator_node` được thiết kế để kiểm tra và xử lý `retry_count`. Tuy nhiên, logic hiện tại là dạng "skeleton" (khung): nó đang tự động trả về `PASS` và reset `"retry_count": 0`, sau đó đi tiếp đến `current_task_idx + 1`.
- **Cấp độ LLM (Thực tế đang xảy ra):** Khi LLM "cắm đầu làm" và "fail", LangChain có cơ chế tự động thử lại (ví dụ: lỗi parse JSON, gọi tool sai định dạng). Những lần retry này diễn ra bên trong hàm `.invoke()` hoặc `.ainvoke()` của Agent, in thẳng lỗi ra terminal rồi tự gọi lại mô hình. 
- **Góc nhìn dev/user:** Vì log terminal chỉ hiện lỗi nội bộ LangChain mà không nói rõ là đang "lùi về node Planner" hay "Agent tự gọi lại LLM", nên người xem không biết hệ thống đang sửa sai kiểu gì.

## 4. Quyết định Kỹ thuật và Hướng giải quyết

Sau khi cân nhắc giữa việc lưu vào `GlobalState` / `AgentState` và việc làm nặng hệ thống (State Bloat), kiến trúc đã được định hình theo hướng: **Sử dụng Streaming qua WebSocket cho các sự kiện (Events) thay vì lưu tĩnh vào Database.**

1. **Sử dụng LangChain Event Streaming (astream_events):**
   - Thay vì chỉ chờ `.ainvoke()` chạy xong toàn bộ Graph, chúng ta chuyển sang dùng `.astream_events()` của LangGraph.
   - Để tránh làm rối giao diện người dùng (UI spam), hệ thống sẽ **chỉ bắt các sự kiện ở cấp độ function/tool call** (Ví dụ: agent bắt đầu chạy, tool đang được gọi, tool báo lỗi, agent gọi lại LLM). Bỏ qua các sự kiện sinh text từng chữ (token streaming).

2. **Cập nhật API / Websocket (Không lưu DB):**
   - Xây dựng một Connection Manager để quản lý các kết nối WebSocket đang mở, map theo `run_id`.
   - Backend sẽ chủ động đẩy (push) các event log này qua WebSocket ngay khi `astream_events` emit ra.
   - Vì chỉ dùng cho mục đích UI UX và dễ debug, các log này sẽ mang tính chất "ephemeral" (phù du), không lưu ngược lại vào Database. Người dùng F5 lại trang sẽ mất live stream cũ, nhưng vẫn giữ được các mốc trạng thái chính từ API Get State tĩnh.

**Kết luận:** Quyết định này giúp hệ thống tách biệt rõ ràng giữa **State (Kết quả mốc)** và **Events (Dòng thời gian sự kiện)**. Frontend được làm phong phú bởi Live Logs mà Backend vẫn giữ được hiệu năng cao, tránh phình to kích thước Checkpointer.
