# Null Agent — Fill Strategy (v3)

---

## Ràng buộc hệ thống

- Không thực hiện encoding
- Không được drop_column trong bất kỳ tình huống nào
- Nếu allow_missing = True và null_ratio = 100% → fill_constant hoặc keep_null
- Bỏ qua fill_llm

---

## Bảng Option Fill theo Semantic Type

| Type | Fill Strategy | Điều kiện |
|------|---------------|-----------|
| **Continuous** | `fill_mean/median` | null_ratio < 100% |
| **Discrete** | `fill_mode` | null_ratio < 100% |
| | `fill_mean/median` (làm tròn số nguyên) | null_ratio < 100% |
| **Nominal** | `fill_mode` | null_ratio < 100% |
| **Ordinal** | `fill_mode` | null_ratio < 100% |
| **Temporal** | `fill_mean/median` | null_ratio < 100% |
| **Free text + Geospatial** | `keep_null` | allow_missing = True |
| **Structured text** | `drop_row` | allow_missing = False |
| | `keep_null` | allow_missing = True |
| **Boolean** | `fill_mode` | null_ratio < 100% |
| | `fill_constant` | null mang nghĩa absence |
| **Identifier** | `drop_row` | không bao giờ fill |

---

## Xử lý khi null_ratio = 100%

Khi null_ratio = 100%, không có giá trị nào trong cột để tính fill_mean, fill_median, fill_mode. Chỉ còn hai lựa chọn:

| allow_missing | Xử lý |
|---------------|-------|
| True | `fill_constant` nếu user define giá trị mặc định, ngược lại `keep_null` |
| False | `fill_constant` nếu user define giá trị mặc định, ngược lại `HITL` |

---

## Các trường hợp option fill không thể thực hiện

### fill_mean / fill_median — không thể thực hiện khi:
- null_ratio = 100% → không có giá trị để tính
- dtype không phải số → Nominal, Ordinal, Boolean, Identifier, Free text, Structured text không tính được mean/median

### fill_mode — không thể thực hiện khi:
- null_ratio = 100% → không có giá trị để tính mode

### fill_constant — luôn thực hiện được
- Giá trị được define sẵn, không phụ thuộc vào data

---

## Lưu ý quan trọng

**Discrete**
fill_mean/median có thể trả về số thập phân (VD: 24.5). Cần làm tròn về số nguyên gần nhất sau khi tính. Ưu tiên fill_mode vì luôn trả về số nguyên hợp lệ có trong dữ liệu.

**Ordinal**
Không dùng fill_mean/median vì không thực hiện encoding. Chỉ dùng fill_mode.

**Boolean**
Dùng fill_constant khi null mang nghĩa vắng mặt (absence). Ví dụ `has_discount = null` có nghĩa không có giảm giá → điền False. Nếu không chắc thì dùng fill_mode.

**Identifier**
Tuyệt đối không fill dưới bất kỳ hình thức nào vì sẽ tạo ra key giả, gây sai lệch toàn bộ downstream.

**Free text + Geospatial**
Không có fill strategy khả thi nào ngoài fill_constant nếu user define. Mặc định keep_null.
