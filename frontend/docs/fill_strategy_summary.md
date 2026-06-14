# Bảng Tổng Hợp Fill Strategy theo Data Type

## Bảng chính

| Type | Ví dụ | Fill Strategy |
|------|-------|---------------|
| **Continuous** | price, height, temp | `fill_mean` — phân phối chuẩn, không có outlier |
| | | `fill_median` — có outlier hoặc phân phối skewed |
| **Discrete** | count, age, quantity | `fill_median` — ưu tiên |
| | | `fill_mode` — nếu giá trị tập trung rõ ràng |
| **Nominal** | color, country, gender | `fill_mode` — nếu top_freq_ratio > 0.4 |
| | | `fill_llm` — nếu phân phối đều |
| **Ordinal** | rating, edu_level | `fill_mode` — giá trị xuất hiện nhiều nhất |
| | | `fill_median` — sau khi encode thành số |
| **Temporal** | created_at, birth_date | `fill_median` — mốc thời gian trung vị |
| **Free text + Geospatial** | description, note, address, lat/lng | `fill_llm` |
| **Structured text** | email, phone, URL | `fill_llm` — nếu có đủ context tham chiếu |
| | | `drop_row` — nếu không thể suy luận được |
| **Boolean** | is_active, has_discount | `fill_mode` |
| | | `fill_constant` — nếu null mang nghĩa absence |
| **Identifier** | user_id, order_id | `drop_row` — không bao giờ fill |

---

## Lưu ý quan trọng

### Ordinal
Không dùng `fill_mean` vì khoảng cách giữa các bậc không đều. Ví dụ `low/medium/high` encode thành `1/2/3` nhưng không có nghĩa là khoảng cách giữa các bậc là bằng nhau.

### Structured text
Ưu tiên `fill_llm` khi có đủ context để suy luận. Ví dụ: biết `first_name`, `last_name`, `company` thì LLM có thể đoán được `email`. Nếu không đủ context thì `drop_row` an toàn hơn fill sai.

### Boolean
Dùng `fill_constant` khi null thực sự mang nghĩa vắng mặt (absence), ví dụ `has_discount = null` có nghĩa là không có giảm giá → điền `False`. Nếu không chắc thì dùng `fill_mode`.

### Identifier
Tuyệt đối không fill dưới bất kỳ hình thức nào vì sẽ tạo ra key giả, gây sai lệch toàn bộ downstream (join, dedup, tracking).

---

## Điều kiện chọn giữa fill_mean và fill_median (Continuous)

| Điều kiện | Strategy |
|-----------|----------|
| Phân phối chuẩn, skewness < 1.0, không có outlier | `fill_mean` |
| Skewness > 1.0 hoặc < -1.0 | `fill_median` |
| Phát hiện outlier qua IQR | `fill_median` |

---

## Điều kiện chọn giữa fill_mode và fill_llm (Nominal)

| Điều kiện | Strategy |
|-----------|----------|
| top_freq_ratio > 0.4 | `fill_mode` |
| top_freq_ratio ≤ 0.4 và có đủ context columns | `fill_llm` |
| top_freq_ratio ≤ 0.4 và không đủ context | `keep_null` |
