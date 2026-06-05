# Tài liệu Cấu trúc & Tính năng Cơ sở Dữ liệu (PostgreSQL Lineage)

Tài liệu này mô tả chi tiết về cách dự án Agentic-Data-Cleaner sử dụng PostgreSQL để quản lý Dữ liệu (Data) và Gia phả Dữ liệu (Data Lineage) của quá trình ETL và Data Cleaning thông qua các Agents.

---

## 1. Tổng quan Kiến trúc

Trong một hệ thống Multi-Agent, một file dữ liệu (ví dụ CSV/Excel) có thể đi qua nhiều chặng xử lý khác nhau (VD: *Ingestion Agent -> Null-Cleaning Agent -> Formatting Agent*). Việc theo dõi xem dòng dữ liệu nào đã bị thay đổi bởi Agent nào, ở bước nào là cực kỳ quan trọng. 

Hệ thống lưu trữ của chúng ta giải quyết bài toán này bằng cơ chế **Versioning (Phiên bản)** kết hợp với kiểu dữ liệu **JSONB**. Mọi lần lưu, dữ liệu cũ vẫn được giữ nguyên, và hệ thống chỉ sinh ra các bản ghi (records) với chỉ số `version` cao hơn.

---

## 2. Thiết kế Cơ sở Dữ liệu (Schema)

Hệ thống sử dụng SQLAlchemy ORM (phiên bản 2.0+) thông qua `psycopg` driver. Schema gồm 3 bảng chính (được định nghĩa trong `app/models/lineage.py`):

### 2.1. Bảng `sessions`
Đóng vai trò là thẻ định danh chung cho một tệp dữ liệu từ lúc được import cho tới lúc kết thúc pipeline.
* **id** `UUID` (Primary Key): Mã định danh duy nhất của phiên làm việc.
* **dataset_name** `String`: Tên file hoặc tên bộ dữ liệu ban đầu.
* **created_at** `DateTime`: Thời gian import.

### 2.2. Bảng `lineage_versions`
Ghi nhận "Lịch sử đóng góp" của từng Agent đối với tập dữ liệu.
* **id** `UUID` (Primary Key).
* **session_id** `UUID` (Foreign Key): Trỏ về bảng `sessions`.
* **version** `Integer`: Số phiên bản của dữ liệu (1, 2, 3...).
* **agent_name** `String`: Tên Agent đã tạo ra phiên bản này (VD: `ingestion_agent`, `cleaner_agent`).
* **description** `String`: Ghi chú về những gì Agent đã thực hiện.
* **created_at** `DateTime`: Thời gian tạo phiên bản.

### 2.3. Bảng `dataset_records` (Trung tâm Dữ liệu)
Bảng này lưu trữ toàn bộ nội dung của Dataframe dưới định dạng JSONB để đảm bảo tính linh hoạt vô hạn với mọi cấu trúc cột.
* **id** `UUID` (Primary Key).
* **session_id** `UUID` (Foreign Key): Trỏ về bảng `sessions`.
* **version** `Integer`: Cho biết dòng dữ liệu này thuộc phiên bản nào.
* **row_index** `Integer`: Số thứ tự gốc của dòng dữ liệu trong DataFrame (dùng để sort và tracking 1-1).
* **data** `JSONB`: Cột linh hoạt lưu toàn bộ nội dung của dòng dưới dạng Key-Value (ví dụ: `{"name": "Nguyen A", "age": 25}`).

---

## 3. Tại sao lại là JSONB?

1. **Schema-less**: Dữ liệu từ các file CSV/Excel khác nhau sẽ có các tập hợp cột khác nhau. Việc lưu dưới dạng JSONB cho phép hệ thống nạp mọi loại dữ liệu mà không cần phải can thiệp lệnh `ALTER TABLE` trong cơ sở dữ liệu.
2. **Khả năng truy vấn (Queryable)**: Dù là JSON, PostgreSQL vẫn hỗ trợ Indexing (GIN Index) và cho phép query trực tiếp vào các key bên trong (VD: `SELECT data->>'age' FROM dataset_records`).
3. **Phù hợp với Lineage**: Rất dễ dàng để truy vấn cùng một `row_index` nhưng ở 2 `version` khác nhau để so sánh trực tiếp xem Agent đã làm biến đổi cột nào của dòng đó.

---

## 4. Giao diện Lập trình (API) - LineageService

Mọi tương tác lưu/đọc dữ liệu từ DB đều được trừu tượng hóa qua class `LineageService` (`app/services/lineage_service.py`), giúp các Agent không cần quan tâm tới SQLAlchemy hay SQL thuần.

### 4.1. Lưu một Version mới (Lưu dữ liệu vào DB)
Khi một Agent xử lý xong DataFrame, nó sẽ dùng hàm `append_new_version` để tự động tạo một version mới dựa trên Max Version hiện tại.

```python
from app.services.lineage_service import LineageService
import uuid
import pandas as pd

session_id = uuid.UUID("42deca96-17c1-41be-94cf-7c5f6f9c0c74")
df = pd.DataFrame([{"col1": "A", "col2": 1}, {"col1": "B", "col2": 2}])

# Hệ thống tự động tính toán ra new_version, lưu metadata và bulk insert toàn bộ df
new_version = LineageService.append_new_version(
    session_id=session_id,
    df=df,
    agent_name="Data_Cleaner_Agent",
    description="Removed null values"
)
```
*Ghi chú kỹ thuật*: Hàm này sử dụng `db.bulk_save_objects` cho tốc độ ghi cực nhanh, và đã tích hợp sẵn `db.flush()` để tránh lỗi ForeignKeyViolation khi đẩy dữ liệu vào Postgres.

### 4.2. Lấy DataFrame từ Version mới nhất (Load từ DB)
Dành cho các Agent muốn bốc dữ liệu mới nhất ra để làm việc tiếp.

```python
df_latest = LineageService.get_latest_version(session_id)
# df_latest là một đối tượng pandas.DataFrame hoàn chỉnh
```

### 4.3. Lấy DataFrame từ một Version cụ thể (Phục vụ truy xuất quá khứ)
Dành cho các tính năng xem lại lịch sử (Rollback) hoặc so sánh (Diffing).

```python
df_v1 = LineageService.get_version(session_id, version=1)
```

---

## 5. Kết nối & Khởi tạo

* Cấu hình kết nối được đọc từ biến môi trường `postgres_url` thông qua file `.env`.
* Driver sử dụng: `postgresql+psycopg://`
* Để hệ thống bắt đầu chạy, phải đảm bảo các bảng đã được khởi tạo thông qua lệnh `init_db()` trong `app/core/database.py` hoặc các công cụ Migration (như Alembic) trong tương lai.
