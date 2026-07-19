# Type casting order and null-strategy HITL

## Mục tiêu

Thay đổi này đảm bảo pipeline xác định kiểu dữ liệu cuối cùng trước khi xử lý null và không cho worker tự thay đổi strategy đã được duyệt. Thứ tự thực thi mới là:

```text
deduplication -> type_casting -> null_handling
```

Nếu null strategy không phù hợp với semantic type hoặc kiểu dữ liệu cuối cùng của cột, Planner tạo một checkpoint HITL. Các strategy thông thường không hợp lệ phải được thay bằng một option đã được Input Validator kiểm định. Riêng `fill_value` được phép giữ lại như một ngoại lệ có chủ ý của người dùng.

## 1. Type casting chạy trước null handling

Planner tạo danh sách task đang hoạt động theo thứ tự cố định sau:

```python
_EXECUTION_ORDER = ["deduplication", "type_casting", "null_handling"]
```

API cũng dùng cùng thứ tự khi tái tạo `task_list` sau khi người dùng sửa và duyệt plan:

```python
def _active_task_list_from_plan(plan: ExecutionPlan) -> list[str]:
    ordered_task_ids = ["deduplication", "type_casting", "null_handling"]
    active = {
        wrapper.work_order.task_id
        for wrapper in plan.task_list
        if not wrapper.work_order.skip
    }
    return [task_id for task_id in ordered_task_ids if task_id in active]
```

Graph không hard-code thứ tự worker. `route_to_current_task` đọc trực tiếp `state.task_list`, vì vậy hai danh sách trên quyết định thứ tự chạy thực tế.

## 2. Xác định final dtype trước khi kiểm tra fill strategy

Planner xác định kiểu dữ liệu mà null worker sẽ nhận theo quy tắc:

1. Nếu plan có type-casting task đang hoạt động cho cột, dùng `expected_type` trong type-casting strategy.
2. Nếu người dùng không cast cột, dùng physical `dtype` trong statistical context.

```python
@classmethod
def _planned_final_dtype(
    cls, plan: ExecutionPlan, null_task: TaskDetail, column: str
) -> str:
    type_task = next(
        (
            wrapper.work_order
            for wrapper in plan.task_list
            if wrapper.work_order.task_id == "type_casting"
            and not wrapper.work_order.skip
        ),
        None,
    )
    if type_task is not None:
        type_strategy = cls._strategy_dict(type_task)
        type_config = (type_strategy.get("per_column") or {}).get(column) or {}
        expected_type = type_config.get("expected_type")
        if expected_type:
            return str(expected_type).lower()

    if null_task.inputs and column in null_task.inputs.column_context:
        statistical = null_task.inputs.column_context[column].statistical
        dtype = statistical.get("dtype")
        if dtype:
            return str(dtype).lower()
    return "unknown"
```

`fill_mean` và `fill_median` chỉ được đề xuất khi final dtype là numeric hoặc temporal:

```python
@staticmethod
def _strategy_supported_by_final_dtype(strategy: str, final_dtype: str) -> bool:
    if strategy not in {"fill_mean", "fill_median"}:
        return True
    numeric_or_temporal_markers = (
        "int", "float", "double", "number", "decimal", "date", "datetime",
    )
    return any(marker in final_dtype for marker in numeric_or_temporal_markers)
```

Ví dụ, một cột có semantic type `Continuous` nhưng đang là `object`:

- Nếu người dùng đồng ý cast sang `float`, Planner có thể đề xuất `fill_mean` và `fill_median`.
- Nếu người dùng từ chối cast, final dtype vẫn là `object`; hai strategy trên không được đưa vào lựa chọn HITL.

## 3. Tái sử dụng options của Input Validator

Planner đọc lại câu hỏi `Q2_strategy_column_<column>` và lấy danh sách `options` mà Input Validator đã hiển thị:

```python
prefix = "Q2_strategy_column_"
for key, question in null_questions.items():
    if not key.startswith(prefix) or not question:
        continue
    question_dict = question if isinstance(question, dict) else question.model_dump()
    options_by_column[key[len(prefix):]] = list(question_dict.get("options") or [])
```

Nếu cột không từng phát sinh clarification question, Planner dùng `fill_strategies` trong semantic profile làm fallback. Các options sau đó được lọc lại theo final dtype để phản ánh quyết định casting cuối cùng.

Planner không đưa `fill_llm` vào review vì null worker hiện chưa thực thi strategy này. `drop_column` đã bị loại hoàn toàn khỏi contract tạo plan. Nếu một plan cũ hoặc output bất thường vẫn chứa strategy không được hỗ trợ, Planner bắt buộc tạo HITL với fallback `leave_as_is` thay vì bỏ qua conflict. Nếu `fill_value` được chọn, giao diện hiển thị thêm ô nhập constant và gửi cả strategy lẫn constant về API.

## 4. Quy tắc giữ hoặc thay strategy

Khi strategy hiện tại không thuộc tập options hợp lệ:

```python
can_keep_current = current == "fill_value"
options = (
    [current, *[option for option in compatible if option != current]]
    if can_keep_current
    else compatible
)
```

Ý nghĩa:

- `fill_mean`, `fill_median` hoặc strategy thông thường khác bị sai logic: không xuất hiện lựa chọn giữ nguyên. Người dùng phải chọn một option hợp lệ.
- `fill_value`: vẫn xuất hiện lựa chọn giữ nguyên vì đây có thể là default/sentinel có chủ ý như `"Unknown"`. Người dùng cũng có thể chuyển sang một option được hệ thống đề xuất.
- Nếu `fill_value` được giữ lại, giá trị constant ban đầu trong `strategy.per_column[column].fill_value` không bị thay đổi.

## 5. HITL bắt buộc trước khi chạy worker

Nếu plan có null-strategy conflict, API không cho approve plan mà thiếu `null_review`:

```python
if null_review_required and (payload is None or payload.null_review is None):
    raise HTTPException(
        status_code=400,
        detail="Null strategy compatibility decisions are required before execution.",
    )
```

API cũng yêu cầu quyết định cho tất cả cột đang có conflict và chỉ chấp nhận option đã được Planner cung cấp:

```python
missing_decisions = set(offered) - set(null_review.strategies)
if missing_decisions:
    raise HTTPException(
        status_code=400,
        detail=f"Missing null strategy review decisions for columns: {sorted(missing_decisions)}",
    )

for column, selected in null_review.strategies.items():
    if column not in offered or selected not in offered[column]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid null strategy review selection for column '{column}'.",
        )
    per_column[column]["strategy"] = selected
```

Sau khi duyệt, lựa chọn được ghi trực tiếp vào `execution_plan.task_list[].work_order.strategy`. Worker chỉ đọc plan đã cập nhật và thực thi strategy đó.

## 6. Giao diện review

Execution Plan Panel hiển thị một dropdown cho từng cột có conflict. Giá trị mặc định là:

- Strategy hiện tại nếu đó là `fill_value`.
- Option hợp lệ đầu tiên nếu strategy hiện tại là một strategy sai logic không được phép giữ.

Khi nhấn **Approve & Execute Cleaning**, frontend gửi toàn bộ lựa chọn dưới dạng:

```json
{
  "null_review": {
    "strategies": {
      "column_name": {
        "strategy": "fill_value",
        "fill_value": "Unknown",
        "allow_pattern_mismatch": true,
        "allow_dmv_sentinel": true
      }
    }
  }
}
```

## 7. Trách nhiệm của worker

Null worker không còn semantic coercion. Nhánh thực thi sử dụng trực tiếp strategy trong plan:

```python
# The planner's strategy is authoritative. Compatibility checks belong
# to input validation/planning; workers must not silently replace it.
if strategy == "drop_row":
    ...
elif strategy == "fill_value":
    ...
elif strategy == "fill_mode":
    ...
elif strategy == "fill_mean":
    ...
elif strategy == "fill_median":
    ...
```

Ranh giới trách nhiệm cuối cùng là:

```text
Input Validator: tạo các lựa chọn fill hợp lệ
Planner: kết hợp quyết định casting, xác định final dtype và tổ chức HITL
Plan approval API: ghi lựa chọn cuối cùng vào execution plan
Worker: thực thi đúng strategy đã được duyệt
```

## 8. Override pattern và disguised-missing validation cho fill_value

Khi constant không khớp `expected_str_pattern` hoặc thuộc `potential_dmv`, Planner tạo warning trước execution. Người dùng phải nhập lại constant hoặc xác nhận riêng từng xung đột. API kiểm tra lại quyết định và ghi bằng chứng xác nhận vào cấu hình cột:

```json
{
  "strategy": "fill_value",
  "fill_value": "Unknown",
  "validation_overrides": {
    "expected_str_pattern": {
      "allow_fill_value_mismatch": true,
      "acknowledged_value": "Unknown",
      "acknowledged_by_user": true
    },
    "potential_dmv": {
      "allow_fill_value_as_sentinel": true,
      "acknowledged_value": "Unknown",
      "acknowledged_by_user": true
    }
  }
}
```

Deterministic validator chỉ miễn rule khi `acknowledged_value` vẫn bằng đúng `fill_value` trong plan. Nếu constant bị thay đổi sau approval, override cũ không còn hiệu lực.
