# 5.6 Triển khai Output Validator Agent – Tác tử kiểm định kết quả

Output Validator Agent là nút kiểm định được thực thi sau mỗi worker trong pipeline. Tác tử không trực tiếp làm sạch dữ liệu mà đánh giá liệu worker vừa chạy có hoàn thành đúng work order do Planner quy định hay không. Cơ chế kiểm định gồm hai tầng: tầng luật xác định bằng Pandas để kiểm tra các điều kiện định lượng của kế hoạch và tầng LLM để diễn giải kết quả trong đúng phạm vi tác vụ, chấm điểm chất lượng và đưa ra gợi ý sửa lỗi. Validator Node sử dụng kết quả này để quyết định chuyển sang worker tiếp theo, chạy lại worker hiện tại hoặc yêu cầu Planner lập kế hoạch mới.

## Luồng xử lý

Khi một worker hoàn tất, Validator Node trước hết xác định tác vụ đang hoạt động từ `current_task_idx` và lấy work order tương ứng trong `ExecutionPlan`. Sau đó, node khởi tạo `ValidatorAgent` và truyền vào trạng thái chung của pipeline. Validator Agent đọc đường dẫn DataFrame đầu ra từ `path_file_to_validate` hoặc `physical_dataframe_path`, đồng thời lấy yêu cầu người dùng, thông tin làm rõ, kế hoạch của tác vụ hiện hành và tên worker vừa thực thi. Trước khi gọi LLM, agent chạy kiểm định xác định bằng Pandas dựa trên các `checks` và `success_metrics` đã có trong work order. Kết quả kiểm định này, cùng với các thông tin ngữ cảnh, được gửi tới LLM; nếu cần quan sát thêm chất lượng tổng thể của dữ liệu, LLM có thể gọi công cụ kiểm tra chất lượng. LLM sau đó trả về kết quả có cấu trúc gồm trạng thái đạt/không đạt, điểm chất lượng, các quy tắc lỗi và gợi ý lập kế hoạch lại. Nếu tác vụ đạt, Validator Node khôi phục định dạng ngày giờ khi cần, lưu phiên bản dữ liệu đã được phê duyệt vào lineage, tăng chỉ số tác vụ và chuyển pipeline sang worker tiếp theo. Nếu tác vụ không đạt, node tăng bộ đếm retry; tác vụ được chạy lại khi chưa vượt số lần thử tối đa, còn khi đã hết số lần thử, node lưu lỗi và gợi ý rồi điều hướng về Planner để sinh kế hoạch mới.

## Input/Output

| Hướng | Nội dung | Định dạng |
|---|---|---|
| Input | DataFrame sau worker | Đường dẫn `path_file_to_validate` hoặc `physical_dataframe_path` tới CSV/Parquet |
| Input | Tác vụ hiện hành | `TaskDetail` được lấy từ `ExecutionPlan.task_list` theo `current_task_idx` |
| Input | Tiêu chí kiểm định | `verification.checks`, `success_metrics` và chiến lược của work order |
| Input | Hồ sơ ngữ nghĩa | `semantic_profile`, dùng để kiểm tra DMV và pattern kỳ vọng của cột |
| Input | Ngữ cảnh người dùng | `user_prompt` và `raw_requirement_input` chứa yêu cầu, quyết định làm rõ |
| Input | Trạng thái điều phối | `retry_count`, giới hạn `max_retries_per_task`, phiên bản dữ liệu và session lineage |
| Output | Kết quả đánh giá LLM | `ValidatorOutput`: `passed`, `quality_score`, `score_breakdown`, `failed_rules`, `replan_hints`, `reasoning` |
| Output | Kết quả kiểm định trong state | `ValidationResultItem` trong `validation_results`, bao gồm worker, task, trạng thái đạt, lỗi và hành động đề xuất |
| Output khi đạt | Phiên bản dữ liệu được phê duyệt | Phiên bản mới trong LineageService, cập nhật `dataset_version`, `current_dataset_version`, tăng `current_task_idx` và reset `retry_count` |
| Output khi không đạt | Thông tin retry/replan | `last_validation_error`, `failed_task_id`, `replan_reason`, `replan_hints` và trạng thái điều hướng phù hợp |

## Thiết kế chi tiết

### Kiểm định theo phạm vi tác vụ

Validator Agent chỉ đánh giá mục tiêu của worker vừa chạy. Ví dụ, sau Deduplication Agent, các giá trị null còn lại không làm giảm điểm vì xử lý null thuộc trách nhiệm của Null Handling Agent. Nguyên tắc này ngăn Validator đánh giá cả bộ dữ liệu như một tác vụ duy nhất và bảo đảm điểm chất lượng phản ánh đúng kết quả của từng bước trong pipeline.

### Tầng kiểm tra xác định bằng Pandas

Hàm `run_pandas_validation(...)` đọc DataFrame đầu ra và kiểm tra các tiêu chí do Planner tạo. Các kiểm tra hiện có gồm số dòng trùng phải bằng 0, cột khóa phải duy nhất, tỷ lệ null không vượt ngưỡng, DataFrame không còn exact duplicate, giá trị thiếu giả dạng (DMV) đã được xử lý và giá trị điền phải khớp pattern kỳ vọng khi cần. Với null handling, các kiểm tra được điều chỉnh theo chiến lược đã chọn: cột được phép `leave_as_is` không bị ép null rate về 0; nếu kế hoạch yêu cầu `drop_column`, validator kiểm tra cột đã được xóa. Kết quả trả về là chuỗi `SUCCESS`, `FAILED` kèm danh sách rule, hoặc `ERROR` khi không thể chạy kiểm định.

### Tầng đánh giá ngữ cảnh bằng LLM

LLM nhận kết quả Pandas như bằng chứng chính và chỉ dùng công cụ chất lượng dữ liệu khi cần quan sát thêm. Mô hình chấm `quality_score` từ 0 đến 100 dựa trên mức độ worker hoàn thành nhiệm vụ và mức độ tác động phụ lên dữ liệu. Điểm từ 80 trở lên tương ứng với đạt; dưới 80 là không đạt. Khi không đạt, LLM phải trả `replan_hints` rõ ràng để worker retry hoặc Planner sửa chiến lược, thay vì chỉ trả thông báo lỗi chung chung.

### Điều phối self-correction

Nếu `passed = true`, Validator Node reset `retry_count`, tăng `current_task_idx` và cho phép pipeline tiếp tục. Khi tác vụ vừa xử lý null đạt, node có thể khôi phục định dạng hiển thị ban đầu của các cột ngày giờ trước khi lưu artifact được phê duyệt. Sau đó, `LineageService.append_new_version_from_file(...)` lưu phiên bản chính thức, bảo đảm chỉ dữ liệu qua kiểm định mới trở thành phiên bản lineage tiếp theo.

Ngược lại, nếu `passed = false`, Validator Node tăng `retry_count`. Khi số lần thử chưa đạt giới hạn `max_retries_per_task` trong `global_constraints`, pipeline quay lại chạy worker hiện hành. Khi đã đạt giới hạn, node điều hướng `next_node = planner`, đồng thời truyền `last_validation_error`, `failed_task_id`, `replan_reason` và `replan_hints` để Planner tránh lặp lại chiến lược đã thất bại.

## Thiết kế cài đặt

| Thành phần | Công nghệ/thư viện | Vai trò |
|---|---|---|
| Kiểm định xác định | Pandas | Đọc artifact và thực thi các rule định lượng trong work order |
| Suy luận đánh giá | LangChain + LLM từ `create_llm()` | Đánh giá theo ngữ cảnh của tác vụ, chấm điểm và sinh gợi ý sửa lỗi |
| Công cụ chất lượng | `perform_data_quality_check` | Cung cấp báo cáo tổng thể về null, duplicate, DMV và issue khi LLM cần quan sát thêm |
| Schema | Pydantic v2 | `ValidatorOutput`, `ValidationCheck`, `TaskVerification`, `ValidationResultItem` |
| Điều phối | LangGraph | `validator_node` quyết định pass, retry hoặc replan và cập nhật `GlobalState` |
| Truy vết | LineageService | Lưu phiên bản dữ liệu chỉ sau khi validation pass |

| Class/hàm | Vai trò |
|---|---|
| `ValidatorAgent` | Tác tử thực hiện kiểm định lai Pandas + LLM cho output của worker. |
| `ValidatorAgent.run(state)` | Thu thập ngữ cảnh, chạy Pandas validation, gọi LLM/tool và trả `ValidatorOutput`. |
| `run_pandas_validation(...)` | Đọc tệp đầu ra, thực thi các rule của work order và trả kết quả tóm tắt. |
| `validate_dataframe(...)` | Triển khai các rule về duplicate, uniqueness, null rate, DMV và pattern. |
| `perform_data_quality_check` | LangChain tool tạo Quality Report tổng thể khi LLM cần quan sát thêm. |
| `validator_node(state)` | Điều phối kết quả pass/fail, retry/replan, khôi phục format datetime và lineage. |
| `ValidatorOutput` | Schema đầu ra của LLM: trạng thái, điểm, lỗi, gợi ý và lý do. |
| `ValidationResultItem` | Schema lưu kết quả kiểm định của một tác vụ trong `GlobalState`. |

## Prompt Design

### System Prompt

System prompt yêu cầu LLM đóng vai trò Output Validator Agent, đánh giá chất lượng dữ liệu sau khi một worker cụ thể đã chạy. Prompt quy định mô hình nhận bốn khối ngữ cảnh: yêu cầu và thông tin làm rõ của người dùng, work order của Planner, tên worker vừa chạy và kết quả kiểm định xác định bằng Pandas.

Phần logic chính của system prompt gồm bốn bước. **Thứ nhất**, mô hình xác định đúng nhiệm vụ của worker hiện hành và chỉ đánh giá các lỗi nằm trong phạm vi nhiệm vụ đó; lỗi thuộc worker khác không được làm giảm điểm. **Thứ hai**, mô hình ưu tiên tin cậy kết quả Pandas: `SUCCESS` cho thấy worker nhiều khả năng đã đạt yêu cầu, còn `FAILED` cho thấy các quy tắc định lượng bị vi phạm. **Thứ ba**, khi cần quan sát thêm, mô hình gọi `perform_data_quality_check` để xem báo cáo chất lượng tổng thể. **Cuối cùng**, mô hình chấm điểm từ 0 đến 100 theo rubric, xác định pass khi điểm từ 80 trở lên và bắt buộc đưa ra `replan_hints` có thể hành động khi thất bại.

### Human Message

Human message được dựng động bằng các khối thông tin sau:

| Khối | Nội dung | Ý nghĩa |
|---|---|---|
| `USER PROMPT` | `user_prompt` | Yêu cầu làm sạch ban đầu của người dùng. |
| `CLARIFICATIONS` | `raw_requirement_input` | Thông tin bổ sung hoặc lựa chọn mà người dùng đã xác nhận. |
| `TASK PLAN` | `TaskDetail` dạng JSON | Mục tiêu, chiến lược và tiêu chí kiểm định của tác vụ đang được đánh giá. |
| `AGENT NAME` | Tên worker vừa chạy | Giới hạn phạm vi đánh giá của LLM vào đúng trách nhiệm của worker đó. |
| `DETERMINISTIC VALIDATION RESULT` | Chuỗi kết quả từ Pandas | Bằng chứng chính về việc các rule trong kế hoạch đã đạt hay chưa. |
| Dataset path | `file_path` | Đường dẫn artifact để LLM gọi tool chất lượng dữ liệu khi cần. |

Human message cũng nhắc lại rằng LLM chỉ được phạt các vấn đề thuộc phạm vi của `AGENT NAME`. Sau khi tool call (nếu có), hệ thống thêm một system message cuối yêu cầu LLM chỉ trả JSON đúng schema `ValidatorOutput`; nhờ đó kết quả có thể được Pydantic kiểm tra và Validator Node sử dụng trực tiếp cho retry hoặc replan.

