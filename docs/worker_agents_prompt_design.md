# Prompt Design của các Worker Agent

Phần này trình bày thiết kế prompt của các worker theo cùng cách mô tả ở Planner Agent: tách thành System Prompt và Human Message, làm rõ các quy tắc bắt buộc và các khối dữ liệu được đưa vào ngữ cảnh. Trong ba worker, Deduplication Agent có gọi LLM khi cần lựa chọn chiến lược; Null Handling Agent và Type Casting Agent thực thi xác định theo kế hoạch nên không sử dụng LLM runtime.

## 1. Deduplication Agent

Prompt của Deduplication Agent được kích hoạt khi chiến lược loại trùng trong kế hoạch chưa đủ thông tin để thực thi an toàn. Mục tiêu của prompt là yêu cầu LLM lựa chọn cách nhận diện bản ghi trùng, thay vì trực tiếp thay đổi DataFrame. Sau khi LLM trả về quyết định, mã nguồn tiếp tục kiểm tra quyết định trên dữ liệu thật trước khi Pandas thực hiện xóa trùng.

### System Prompt

System prompt định hướng LLM đóng vai trò chuyên gia lựa chọn chiến lược loại trùng an toàn trong pipeline làm sạch dữ liệu. Phần mở đầu quy định rằng mô hình phải ưu tiên tránh xóa nhầm dữ liệu hơn là tối đa số lượng bản ghi bị loại bỏ. Từ nguyên tắc này, prompt đặt ra bốn nhóm quy tắc xử lý.

**Bước 1 – Xác định phạm vi và chế độ loại trùng:** Mô hình phải lựa chọn một trong hai chế độ: `exact_full_row`, dùng khi các hàng giống nhau trên toàn bộ cột; hoặc `exact_key`, dùng khi dữ liệu có một tập khóa nghiệp vụ đáng tin cậy. Nếu bằng chứng về khóa không rõ ràng, không đủ hoặc mâu thuẫn, mô hình phải chọn `exact_full_row` thay vì tự suy đoán khóa.

**Bước 2 – Lựa chọn và đánh giá khóa nghiệp vụ:** Khi cân nhắc `exact_key`, mô hình phải gọi công cụ khảo sát để kiểm tra các nhóm trùng trước khi kết luận. Prompt yêu cầu ưu tiên khóa composite gồm nhiều thuộc tính nghiệp vụ, chẳng hạn email kết hợp với số điện thoại, thay vì khóa đơn yếu như họ tên. Các mã kỹ thuật, số thứ tự hoặc định danh nội bộ không được dùng làm khóa nghiệp vụ nếu không có bằng chứng rõ ràng. Tương tự, các cột có tỷ lệ thiếu cao cần được hạn chế vì có thể làm các bản ghi không liên quan bị gom vào cùng một nhóm.

**Bước 3 – Xử lý trường hợp trùng gần đúng:** Khi kế hoạch cho phép fuzzy matching, mô hình có thể đề xuất cột cần so sánh, cách tạo nhóm ứng viên (blocking), cột dùng làm bằng chứng hỗ trợ hoặc phản bác, cùng ngưỡng tương đồng. Prompt quy định fuzzy matching chỉ tạo ra các cặp ứng viên có khả năng trùng để xem xét; mô hình không được sử dụng độ tương đồng mờ làm cơ sở duy nhất để tự động gộp hoặc xóa bản ghi. Nếu bằng chứng yếu hoặc mâu thuẫn, phương án an toàn là quay về `exact_full_row` hoặc yêu cầu người dùng xem xét.

**Bước 4 – Định dạng đầu ra:** Mô hình phải chỉ trả về JSON hợp lệ, không kèm Markdown hay lời giải thích ngoài schema. JSON bao gồm chế độ loại trùng, danh sách cột khóa, mô tả ngữ nghĩa của các cột, cấu hình fuzzy nếu có, độ tin cậy và `reasoning_summary` ngắn. Phần tóm tắt chỉ dùng để giải thích quyết định cho người dùng và log hệ thống, không yêu cầu mô hình trình bày chuỗi suy luận nội bộ.

### Human Message

Human message được tạo động ở mỗi lần chạy và yêu cầu LLM lựa chọn chiến lược loại trùng an toàn nhất. Nội dung chính là khối `Context` ở dạng JSON, bao gồm các thông tin sau:

| Khối thông tin | Trường | Ý nghĩa |
|---|---|---|
| Thông tin dataset | `dataset_path`, `dataset_schema` | Xác định artifact hiện hành và cấu trúc các cột của bảng. |
| Ý định người dùng | `user_prompt` | Bảo đảm chiến lược phù hợp với yêu cầu làm sạch mà người dùng đã đưa ra. |
| Hồ sơ ngữ nghĩa | `table_summary` | Tóm tắt ý nghĩa nghiệp vụ của bảng, hỗ trợ diễn giải đúng vai trò từng cột. |
| Ứng viên định danh | `pk_candidates`, `near_unique_columns` | Gợi ý những cột có thể là khóa hoặc gần duy nhất, nhưng LLM vẫn phải kiểm tra trước khi sử dụng. |
| Cột rủi ro | `high_null_columns` | Danh sách cột có nhiều giá trị thiếu, cần tránh dùng làm khóa loại trùng. |
| Quyết định đã có | `planner_task` | Work order từ Planner; đây là nguồn ưu tiên để LLM không làm trái kế hoạch đã được phê duyệt. |
| Gợi ý kỹ thuật | `suggested_candidate_sets`, `suggested_fuzzy_columns`, `fuzzy_enabled` | Các tập khóa composite/cột fuzzy được hệ thống gợi ý và cờ cho biết có được dùng fuzzy hay không. |
| Hồ sơ cột | `columns` | Thông tin chi tiết theo từng cột để LLM đánh giá khả năng nhận diện thực thể. |

Mỗi phần tử trong `columns` bao gồm `name` (tên cột), `dtype` (kiểu dữ liệu vật lý), `null_rate` (tỷ lệ thiếu), `unique_ratio` (tỷ lệ giá trị duy nhất), `detected_patterns` (mẫu định dạng nhận diện được), `sample_values` (một số giá trị mẫu), `semantic_group` (nhóm logic) và `semantic_description` (mô tả nghiệp vụ). Các thông tin này giúp mô hình phân biệt, ví dụ, giữa một cột email có thể làm định danh và một cột tên chỉ có giá trị tham khảo.

## 2. Null Handling Agent

Null Handling Agent không gọi LLM khi chạy, vì xử lý giá trị khuyết là phép biến đổi cần bảo đảm tính xác định và có thể kiểm chứng. Do đó, tác tử không có System Prompt hoặc Human Message runtime. Vai trò tương ứng của prompt được thay thế bằng `ExecutionPlan` và `SemanticProfile`.

### System Prompt

Không sử dụng system prompt runtime. Các quy tắc thường được đặt trong prompt được mã hóa trực tiếp trong agent: chỉ thực hiện chiến lược do Planner quy định; không được xóa cột; không dùng LLM để tự điền dữ liệu; và không áp dụng chiến lược thống kê cho các cột không phù hợp về ngữ nghĩa. Cụ thể, cột định danh không được điền bằng mean/median/mode; cột thứ bậc và boolean không dùng mean/median; còn cột rỗng hoàn toàn nhưng không được phép thiếu sẽ tạo lỗi để yêu cầu HITL thay vì tự chọn giá trị điền.

### Human Message

Không có human message runtime. Thay vào đó, input có cấu trúc được lấy từ `strategy.per_column` trong work order `null_handling`. Mỗi cột có một chiến lược như `drop_row`, `fill_value`, `fill_mean`, `fill_median`, `fill_mode` hoặc `leave_as_is`. `SemanticProfile` cung cấp thêm `semantic_data_type` và `allow_missing` để agent kiểm tra xem chiến lược đó có phù hợp với bản chất cột hay không.

## 3. Type Casting Agent

Type Casting Agent có định nghĩa `TYPE_AGENT_SYSTEM_PROMPT` trong mã nguồn, nhưng phiên bản hiện tại không gọi LLM trong hàm `run()`. Vì vậy, prompt này được dùng như một contract mô tả trách nhiệm của tác tử; việc ép kiểu thực tế do Pandas thực hiện theo `ExecutionPlan`.

### System Prompt

System prompt quy định Type Casting Agent chỉ chuyển đổi các cột được Planner chỉ định và không được tự đoán thêm kiểu dữ liệu đích. Prompt đặt ra các yêu cầu bảo toàn cấu trúc: số hàng và tên cột phải giữ nguyên, không được xóa cột, giá trị null phải được giữ nguyên. Các kiểu dữ liệu được hỗ trợ gồm `int`, `float`, `str`, `bool`, `date`, `datetime` và `time`.

Prompt cũng quy định cách xử lý lỗi chuyển đổi: nếu giá trị khác null không thể parse sang kiểu mục tiêu, giá trị đó được chuyển thành null và số lượng phát sinh phải được ghi nhận trong báo cáo. Agent phải báo lỗi nếu cột yêu cầu không tồn tại, kiểu dữ liệu đích không được hỗ trợ, work order không cung cấp đủ thông tin hoặc không thể đọc/ghi DataFrame. Nhờ đó, lỗi ép kiểu được chuyển thành thông tin cho Validator hoặc Planner replan, thay vì âm thầm bỏ qua cột cần xử lý.

### Human Message

Không có human message runtime trong phiên bản hiện tại. Input tương ứng với human message được lấy trực tiếp từ work order `type_casting`: trường `strategy.per_column.<column>.expected_type` cho biết kiểu dữ liệu đích của từng cột và `parse_format` là thông tin tùy chọn cho dữ liệu ngày/giờ. Khi work order thiếu kiểu dữ liệu đích, agent dùng `SemanticProfile.columns.<column>.expected_type` làm nguồn dự phòng. Các trường này cung cấp đủ ngữ cảnh để agent ép kiểu mà không cần gọi LLM.

