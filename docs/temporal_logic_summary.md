# Quy Trình Xử Lý Dữ Liệu Thời Gian (Temporal Logic)

Tài liệu này tóm tắt toàn bộ luồng logic hiện tại của hệ thống **Agentic-Data-Cleaner** đối với các cột chứa dữ liệu thời gian (`time`) và cột chứa dữ liệu ngày giờ (`datetime` / hỗn hợp). Luồng xử lý được chia thành 4 giai đoạn cốt lõi: Nhận diện, Đề xuất Chiến lược, Giao tiếp Frontend (HITL), và Thực thi Ép kiểu.

---

## 1. Giai đoạn Nhận diện (Semantic Profiling)

Hệ thống sử dụng các biểu thức chính quy (Regex) trong `profiler_agent.py` để quét qua một tập mẫu (sample) của dữ liệu.

- **Đếm tần suất:** Hệ thống đếm số lượng dòng chứa cả Ngày + Giờ (`datetime_count`) và số lượng dòng CHỈ chứa Giờ (`time_only_count`).
- **Phân loại cột chỉ có Giờ (Pure Time):** Nếu `time_only_count > datetime_count`, cột đó được chốt `expected_type = "time"`.
- **Phân loại cột Ngày Giờ (Datetime):** Nếu `datetime_count >= time_only_count` hoặc không xác định rõ ràng, hệ thống ưu tiên gán `expected_type = "datetime"`.

> [!TIP]
> Điều này đảm bảo rằng các cột vừa có `time` vừa có `datetime` (dữ liệu bị lỗi hoặc điền thiếu) sẽ được gom về chuẩn cao nhất là `datetime` để tránh mất mát thông tin.

---

## 2. Giai đoạn Đề xuất Chiến lược Xử lý (Input Validator Prompts)

Khi gặp các dữ liệu bị trống (Null/Missing) trong các cột này, hệ thống AI (LLM) sẽ bị ràng buộc bởi các quy tắc toán học nghiêm ngặt để gợi ý phương pháp điền:

### Đối với cột `time` (Chỉ chứa Giờ)
- **Tùy chọn cho phép:** `fill_mode` (Giờ xuất hiện nhiều nhất), `fill_value` (Giờ cụ thể), `keep_null`.
- **Nghiêm cấm:** `fill_mean`, `fill_median`.
- **Lý do:** Các đối tượng thời gian nguyên thủy không hỗ trợ các phép tính trung bình một cách trực tiếp trong Pandas.

### Đối với cột `datetime` (Có Ngày Giờ / Hỗn hợp)
- **Tùy chọn cho phép:** `fill_median` (Ngày giờ trung vị), `fill_mode`, `fill_value`, `keep_null`.
- **Nghiêm cấm:** `fill_mean` (Trung bình cộng).
- **Lý do:** Trung bình cộng của ngày tháng có thể dẫn đến các mốc thời gian lệch lạc logic (ví dụ làm tròn sai lệch ngày).

---

## 3. Giai đoạn Tương tác Người dùng (Frontend HITL)

Nếu người dùng chọn điền bằng "Custom value" (Tự nhập tay), Frontend sẽ có một lớp bảo vệ để tự động Format dữ liệu người dùng về chuẩn ISO trước khi đưa vào vòng Validator:

- **Regex siêu việt:** Bắt được các lỗi gõ của người dùng như `8h30`, `07:25`, `8:00 p.m.`, `14:00`.
- **Xử lý cho cột `time`:** Nếu người dùng gõ `8:00 p.m.`, Frontend sẽ tự động chuyển thành chuỗi `20:00:00` và hiển thị lại ngay trên màn hình.
- **Xử lý cho cột `datetime`:** Nếu cột yêu cầu `datetime` nhưng người dùng lười và **chỉ nhập Giờ** (ví dụ: `8:00 p.m.`), hệ thống tự động bọc thêm Ngày Hôm Nay vào. Chuỗi sẽ tự động trở thành `YYYY-MM-DDT20:00:00` để đảm bảo không bị Validator đánh lỗi.

---

## 4. Giai đoạn Thực thi Ép Kiểu (Type Casting Agent)

Sau khi chốt phương án, `TypeCastingAgent` sẽ dịch lại toàn bộ dữ liệu vật lý dưới nền Pandas:

### Đối với cột hỗn hợp (Mixed Time / Datetime) -> Ép về `datetime`
- Hệ thống ưu tiên dùng `pd.to_datetime(..., format="mixed")`.
- Nếu có một số dòng bị **thiếu ngày** (chỉ có `14:30:00`) trong khi các dòng khác có đầy đủ ngày giờ, thuật toán sẽ tự động trích xuất "Ngày" từ các dòng đầy đủ đầu tiên và **ghép/bù Ngày đó vào các dòng bị khuyết**, đảm bảo toàn bộ cột đồng nhất một ngày.

### Đối với cột `time` -> Ép về `datetime.time`
- Sử dụng Pandas: Nếu chuyển đổi thông thường thất bại, hệ thống dùng `pd.to_datetime(..., format="mixed")` sau đó cắt lấy thuộc tính `.dt.time`.
- **Fallback mạnh mẽ:** Nếu dữ liệu quá bẩn và bị trả về `NaT`, một hàm apply thủ công sẽ đi qua từng ô dữ liệu, cố gắng trích xuất và cast ra đúng định dạng object `datetime.time` thuần túy của Python.

---

### Tổng Kết Lợi Ích
Nhờ sự phân tầng rõ rệt này, các cột thuần Giờ sẽ không bị ép sai thành Ngày mặc định của máy tính (như 1970-01-01), và các cột Ngày Giờ sẽ không bị vứt bỏ mất dữ liệu chỉ vì một vài dòng người dùng gõ thiếu ngày.
