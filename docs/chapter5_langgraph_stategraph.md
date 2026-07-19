# 5.3 Triển khai đồ thị điều phối LangGraph StateGraph

Để điều phối các tác tử trong quy trình làm sạch dữ liệu, hệ thống triển khai một đồ thị trạng thái (StateGraph) dựa trên thư viện LangGraph. Đồ thị được lựa chọn thay cho cách gọi tuần tự các hàm vì quy trình xử lý không chỉ gồm các bước tuyến tính mà còn có các điểm phân nhánh: yêu cầu người dùng có thể cần được làm rõ, một tác vụ có thể phải chạy lại sau khi kiểm định thất bại, hoặc toàn bộ kế hoạch phải được lập lại khi chiến lược hiện tại không còn phù hợp. Mọi node trong đồ thị đều đọc và cập nhật một trạng thái chung là `GlobalState`; node kế tiếp được xác định từ các giá trị trong trạng thái này. Cách tổ chức trên giúp tách biệt logic nghiệp vụ của từng tác tử khỏi logic điều phối, đồng thời tạo điều kiện cho cơ chế Human-in-the-Loop, checkpointing và data lineage.

## 5.3.1 Cấu trúc đồ thị và các node xử lý

Đồ thị được khởi tạo trong lớp `GraphBuilder` bằng `StateGraph(GlobalState)` và gồm chín node xử lý: `profiler`, `semantic_profile`, `input_validator`, `planner`, `deduplication`, `null_handling`, `type_casting`, `validator` và `report_agent`. Điểm khởi đầu của đồ thị là Profiler Node. Node này thực hiện phân tích thống kê trên dataset đầu vào và lưu kết quả vào trạng thái chung. Tiếp theo, Semantic Profiler Node diễn giải ý nghĩa nghiệp vụ của các cột từ hồ sơ thống kê. Hai kết quả phân tích này trở thành cơ sở để Input Validator Node đánh giá yêu cầu người dùng và để Planner Node sinh kế hoạch thực thi.

Sau khi kế hoạch được phê duyệt, các tác tử xử lý dữ liệu được gọi theo thứ tự trong `task_list`. Ở phiên bản hiện tại, danh sách tác vụ có thể gồm loại trùng lặp, xử lý giá trị khuyết thiếu và chuẩn hóa kiểu dữ liệu. Mỗi worker chỉ thực hiện một work order cụ thể, sau đó luôn chuyển output sang Validator Node. Chỉ khi output đạt kiểm định, pipeline mới được phép chuyển sang tác vụ kế tiếp. Khi không còn tác vụ cần thực hiện, đồ thị điều hướng đến Report Agent để tổng hợp kết quả và kết thúc phiên xử lý.

Luồng chính của đồ thị được mô tả như sau:

```text
START → Profiler → Semantic Profiler → Input Validator → Planner
      → Worker Agent → Output Validator → Worker Agent tiếp theo / Report Agent → END
```

Về mặt cài đặt, mỗi node chỉ trả về phần dữ liệu thay đổi trong `GlobalState`, ví dụ hồ sơ phân tích, kế hoạch, đường dẫn artifact mới, kết quả kiểm định hoặc log thực thi. Việc chọn node tiếp theo không do agent tự quyết định trực tiếp mà do các hàm điều hướng của đồ thị thực hiện. Nhờ đó, các agent có thể được mở rộng hoặc thay thế mà không làm thay đổi nguyên tắc điều phối chung của hệ thống.

## 5.3.2 Quản lý trạng thái chung và trao đổi dữ liệu giữa các node

`GlobalState` được định nghĩa dưới dạng `TypedDict` và là kênh trao đổi thông tin duy nhất giữa các node. Trạng thái này không chỉ lưu dữ liệu đầu vào mà còn lưu toàn bộ thông tin cần thiết để pipeline có thể tiếp tục sau khi bị tạm dừng, chạy lại một tác vụ hoặc lập kế hoạch mới. Các trường trong state được tổ chức thành các nhóm chức năng như Bảng 5.x.

| Nhóm thông tin | Các trường tiêu biểu | Mục đích sử dụng |
|---|---|---|
| Ngữ cảnh phiên xử lý | `project_id`, `session_id`, `dataset_path`, `original_filename`, `user_prompt` | Xác định phiên chạy, tệp dữ liệu và yêu cầu làm sạch của người dùng. |
| Lược đồ và yêu cầu | `dataset_schema`, `raw_requirement_input`, `dataset_version` | Lưu cấu trúc dataset và thông tin được người dùng làm rõ trong quá trình HITL. |
| Hồ sơ phân tích | `statistical_profile`, `semantic_profile`, `input_validation_result` | Cung cấp ngữ cảnh cho Input Validator, Planner và các worker. |
| Kế hoạch và tiến trình | `execution_plan`, `task_list`, `current_task_idx` | Lưu các work order và xác định tác vụ đang được thực hiện. |
| Artifact dữ liệu | `physical_dataframe_path`, `path_file_to_validate`, `current_dataset_version` | Xác định phiên bản DataFrame hiện hành và artifact cần kiểm định. |
| Kết quả và kiểm định | `worker_states`, `worker_outputs`, `validation_results`, `deduplication_result` | Lưu trạng thái worker, báo cáo biến đổi và kết quả kiểm tra. |
| Điều khiển luồng | `retry_count`, `last_validation_error`, `failed_task_id`, `replan_reason`, `next_node` | Hỗ trợ điều hướng retry và replan. |
| Quan sát và HITL | `messages`, `agent_logs`, `token_metrics`, `hitl_status`, `global_errors` | Theo dõi hội thoại, log, chi phí token, trạng thái phê duyệt và lỗi hệ thống. |

Một số trường của `GlobalState` có tính tích lũy nên được gắn reducer thay vì bị ghi đè bởi node mới. Reducer `add_messages` duy trì lịch sử hội thoại giữa người dùng và hệ thống. Hàm `append_list` được dùng để nối thêm bước hoàn thành, kết quả kiểm định và lỗi phát sinh. Hàm `merge_agent_logs` kết hợp log theo từng agent, trong khi `sum_metrics` cộng dồn lượng token mà các tác tử LLM đã sử dụng. Nhờ các reducer này, trạng thái chung vừa lưu được giá trị mới nhất cần cho điều phối, vừa duy trì được lịch sử cần thiết cho việc truy vết.

DataFrame được truyền giữa các worker thông qua artifact thay vì đưa trực tiếp vào state. Hàm `_load_latest_dataframe_with_source(...)` ưu tiên đọc phiên bản mới nhất đã được lưu trong Data Lineage theo session hiện hành. Nếu chưa tồn tại hoặc không truy cập được lineage, hệ thống mới sử dụng đường dẫn trong work order, `physical_dataframe_path` hoặc `dataset_path`. Cách xử lý này bảo đảm các worker ưu tiên làm việc trên phiên bản dữ liệu đã được kiểm định, đồng thời vẫn hỗ trợ chạy pipeline trong môi trường phát triển không có lineage.

## 5.3.3 Cơ chế điều hướng có điều kiện, HITL và tự sửa lỗi

Các cạnh điều hướng có điều kiện được triển khai nhằm phản ánh những tình huống thực tế của quy trình làm sạch dữ liệu. Sau Input Validator Node, hàm `route_from_input_validator(...)` kiểm tra kết quả xác thực đầu vào. Nếu yêu cầu người dùng còn thiếu thông tin và có câu hỏi làm rõ chưa được trả lời, đồ thị tạm dừng để chờ người dùng phản hồi. Sau khi câu trả lời được cập nhật vào state, pipeline tiếp tục từ checkpoint và chuyển sang Planner Node. Trong chế độ benchmark, hệ thống cũng có thể tạm dừng để người dùng xem xét các quyết định đã được điền trước.

Sau Planner Node, hàm `route_to_current_task(...)` đọc `task_list` và `current_task_idx` để chọn worker phù hợp. Các tác vụ được thực hiện theo thứ tự cố định là loại trùng lặp, xử lý giá trị khuyết và chuẩn hóa kiểu dữ liệu. Các tác vụ được Planner đánh dấu không cần thiết sẽ không xuất hiện trong `task_list`; do đó graph tự bỏ qua chúng. Khi chỉ số tác vụ đã vượt quá số phần tử của danh sách, hệ thống chuyển sang Report Agent thay vì tiếp tục gọi worker.

Sau mỗi worker, Validator Node đánh giá output và hàm `route_from_validator(...)` thực hiện điều hướng tiếp theo. Nếu kiểm định đạt, Validator Node tăng `current_task_idx`; graph vì vậy chuyển sang worker kế tiếp hoặc Report Agent. Nếu kiểm định không đạt nhưng tác vụ vẫn còn lượt thử, `current_task_idx` được giữ nguyên, khiến graph quay lại đúng worker vừa thất bại. Nếu đã hết lượt thử, Validator Node đặt `next_node` thành `planner`; graph khi đó quay về Planner để sinh kế hoạch mới.

Cơ chế tự sửa lỗi được triển khai theo hai tầng là Retry và Replan. Khi validation thất bại, hệ thống tăng `retry_count`, lưu các rule lỗi trong `last_validation_error` và ghi nhận tác vụ lỗi vào `failed_task_id`. Số lần thử tối đa lấy từ `max_retries_per_task` trong `global_constraints` của `ExecutionPlan`, với giá trị mặc định là ba lần. Trong giai đoạn Retry, worker được thực hiện lại trên cùng work order. Nếu số lần thất bại đạt giới hạn, hệ thống tạo `replan_reason` và chuyển các `replan_hints` từ Validator Agent về Planner. Planner sử dụng thông tin này để điều chỉnh chiến lược, tạo lại `ExecutionPlan` và đặt lại `current_task_idx` cùng `retry_count` về 0 trước khi pipeline thực hiện kế hoạch mới.

Human-in-the-Loop được hỗ trợ ở cả mức nghiệp vụ và mức đồ thị. Ở mức nghiệp vụ, Input Validator yêu cầu người dùng làm rõ các quyết định chưa đầy đủ, còn Planner cung cấp kế hoạch để người dùng phê duyệt hoặc chỉnh sửa. Ở mức đồ thị, `GraphBuilder` sử dụng `interrupt_before` mặc định trước các node worker và Report Agent. Khi người dùng phê duyệt kế hoạch thông qua API, hệ thống cập nhật state tại checkpoint, đặt `hitl_status` thành `approved`, sau đó tiếp tục graph với danh sách interrupt rỗng để pipeline hoàn thành phần thực thi còn lại.

## 5.3.4 Checkpointing, Data Lineage và khả năng giám sát

Để bảo đảm pipeline có thể tiếp tục sau khi tạm dừng hoặc khi yêu cầu API kết thúc, StateGraph được biên dịch với Postgres checkpointer. `CheckpointerManager` tạo `AsyncPostgresSaver` bằng chuỗi kết nối PostgreSQL trong cấu hình hệ thống và thực hiện khởi tạo bảng checkpoint khi cần. Mỗi lần chạy được gắn một `thread_id` tương ứng với `run_id`, nhờ đó snapshot của các phiên xử lý được lưu tách biệt.

Khi pipeline dừng ở một checkpoint, API có thể truy xuất snapshot bằng `aget_state(...)`, cập nhật câu trả lời làm rõ hoặc kế hoạch đã được duyệt bằng `aupdate_state(...)`, rồi tiếp tục thực thi từ đúng trạng thái này. Checkpoint vì vậy lưu lại không chỉ vị trí của graph mà còn toàn bộ hồ sơ phân tích, kế hoạch, chỉ số retry, thông tin HITL và các log liên quan. Cơ chế này đặc biệt cần thiết đối với các pipeline dài, nơi người dùng không thể hoặc không nên phải chạy lại từ đầu sau mỗi lần điều chỉnh.

Checkpointing quản lý trạng thái điều phối, còn Data Lineage quản lý các phiên bản dữ liệu. Sau khi một worker hoàn thành, artifact mới chỉ là kết quả tạm thời. Chỉ khi Validator Node trả về trạng thái đạt, `LineageService.append_new_version_from_file(...)` mới được gọi để ghi artifact thành phiên bản chính thức. Nếu validation thất bại, phiên bản đó không được promote vào lineage. Do đó, worker tiếp theo sẽ ưu tiên sử dụng phiên bản dữ liệu đã được kiểm định. Đối với tác vụ xử lý null, Validator Node còn có khả năng khôi phục định dạng hiển thị của cột ngày giờ từ `original_datetime_formats` trước khi lưu phiên bản đã được phê duyệt.

Khả năng giám sát được tích hợp trực tiếp vào cơ chế điều phối. Mỗi node cập nhật `current_step`, `completed_steps` và `agent_logs`, trong đó log lưu thời điểm, tên agent, mức độ và nội dung sự kiện. Các tác tử dùng LLM bổ sung token metrics, sau đó reducer cộng dồn thành chi phí tổng của phiên chạy. Dịch vụ pipeline lắng nghe sự kiện qua `astream_events(...)` và phát các sự kiện bắt đầu node, gọi tool, hoàn tất tool hoặc lỗi qua WebSocket để giao diện cập nhật tiến trình theo thời gian thực. Các trường `worker_states`, `worker_outputs`, `validation_results`, `global_errors` và `f1_metrics` tiếp tục cung cấp dữ liệu cho giao diện hiển thị trạng thái xử lý, thay đổi trên dữ liệu, lỗi kiểm định và kết quả đánh giá cuối cùng.

