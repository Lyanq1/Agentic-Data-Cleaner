# 5.6.2 Cơ chế tự sửa lỗi hai tầng (Retry + Replan)

Sau mỗi worker, Output Validator Agent đánh giá kết quả xử lý theo các tiêu chí trong work order. Nếu dữ liệu không đạt yêu cầu, hệ thống không kết thúc pipeline ngay mà áp dụng cơ chế tự sửa lỗi hai tầng gồm chạy lại worker hiện hành (Retry) và lập kế hoạch mới (Replan). Retry được dùng khi lỗi có thể được khắc phục bằng cách thực thi lại tác vụ với cấu hình hiện có; Replan được kích hoạt khi tác vụ đã thất bại nhiều lần liên tiếp, cho thấy chiến lược trong kế hoạch có thể không còn phù hợp với dữ liệu thực tế.

## Các biến trạng thái và cấu hình

| Thành phần | Ý nghĩa |
|---|---|
| `current_task_idx` | Chỉ số của tác vụ đang thực thi trong `task_list`. Chỉ số này được giữ nguyên khi retry và tăng lên khi validation đạt. |
| `retry_count` | Số lần chạy lại của tác vụ hiện hành sau khi validation thất bại. |
| `last_validation_error` | Nội dung lỗi của lần kiểm định gần nhất, gồm các rule thất bại và lý do từ Validator Agent. |
| `failed_task_id` | Mã tác vụ không đạt kiểm định, ví dụ `deduplication`, `null_handling` hoặc `type_casting`. |
| `replan_reason` | Lý do yêu cầu Planner tạo lại kế hoạch. |
| `next_node` | Thông tin điều hướng trong LangGraph; nhận giá trị `planner` khi cần replan. |
| `max_retries_per_task` | Giới hạn số lần retry cho mỗi tác vụ, lấy từ `execution_plan.global_constraints`. Giá trị mặc định là `3`. |

## Luồng xử lý

Khi Validator Agent trả về kết quả không đạt (`passed = false`), Validator Node tăng `retry_count`, tập hợp `failed_rules` và ghi thông tin lỗi vào `last_validation_error`. Nếu số lần thử chưa đạt ngưỡng `max_retries_per_task`, hệ thống giữ nguyên `current_task_idx` và ghi `recommended_next_action = retry_worker` vào `validation_results`. Vì chỉ số tác vụ không đổi, hàm điều hướng của LangGraph đưa pipeline quay lại đúng worker vừa thất bại để thực thi lại work order hiện hành.

Trong trường hợp `retry_count` đạt hoặc vượt ngưỡng cho phép, Validator Node chuyển sang cơ chế Replan. Node lưu mã tác vụ lỗi vào `failed_task_id`, tạo `replan_reason`, gắn `next_node = planner` và ghi các `replan_hints` do Validator Agent cung cấp. LangGraph sau đó điều hướng về Planner Agent. Planner nhận `replan_reason` cùng `last_validation_error` trong ngữ cảnh đầu vào để biết tác vụ nào đã thất bại, những tiêu chí nào chưa đạt và cần thay đổi chiến lược ra sao. Sau khi sinh `ExecutionPlan` mới, Planner đặt lại `current_task_idx = 0` và `retry_count = 0`, từ đó pipeline bắt đầu lại từ tác vụ đầu tiên trong kế hoạch mới.

Ngược lại, khi validation đạt (`passed = true`), Validator Node tăng `current_task_idx` để chuyển sang tác vụ tiếp theo, đặt `retry_count = 0` và xóa `last_validation_error`, `failed_task_id` cùng `replan_reason`. Artifact dữ liệu sau worker chỉ được lưu thành phiên bản chính thức trong Data Lineage sau khi đạt kiểm định; điều này bảo đảm các phiên bản lineage phản ánh những trạng thái dữ liệu đã được phê duyệt.

## Quy tắc điều hướng

| Kết quả validation | Điều kiện | Hành động | Điểm đến tiếp theo |
|---|---|---|---|
| Đạt | `passed = true` | Tăng `current_task_idx`, reset retry và lưu lineage | Worker tiếp theo hoặc Report Agent |
| Không đạt, còn lượt thử | `passed = false` và `retry_count < max_retries_per_task` | Tăng retry, giữ nguyên tác vụ hiện hành | Worker hiện hành |
| Không đạt, hết lượt thử | `passed = false` và `retry_count >= max_retries_per_task` | Lưu lỗi, gợi ý sửa và yêu cầu kế hoạch mới | Planner Agent |

## Thiết kế cài đặt

| Thành phần | Vai trò |
|---|---|
| `validator_node(state)` | Nhận kết quả của Validator Agent, cập nhật retry/replan state và quyết định điều hướng. |
| `_max_retries_per_task(state)` | Lấy giới hạn retry từ `GlobalConstraints`; dùng giá trị mặc định 3 nếu kế hoạch không có cấu hình. |
| `route_from_validator(state)` | Điều hướng sang Planner khi `next_node = planner`; các trường hợp còn lại điều hướng theo `current_task_idx`. |
| `route_to_current_task(state)` | Chọn Deduplication, Null Handling, Type Casting hoặc Report Agent theo task đang hoạt động. |
| `ValidationResultItem` | Lưu trạng thái kiểm định, `failed_rules`, hành động đề xuất và `replan_hints`. |
| `PlannerAgent.run(state)` | Đọc `replan_reason` và `last_validation_error`, sau đó sinh lại kế hoạch thực thi. |

## Lưu ý về chính sách thất bại

Schema của kế hoạch có trường `failure_policy` để mô tả hành động mong muốn khi một tác vụ thất bại. Tuy nhiên, ở phiên bản cài đặt hiện tại, Validator Node quyết định Retry hay Replan chủ yếu dựa trên `retry_count` và `max_retries_per_task`; trường `failure_policy` chưa được đọc trực tiếp trong hàm điều hướng. Vì vậy, giới hạn retry trong `global_constraints` là cấu hình thực sự đang kiểm soát cơ chế tự sửa lỗi.

