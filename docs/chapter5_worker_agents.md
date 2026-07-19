# 5.5 Triển khai các tác tử xử lý làm sạch (Worker Agents)

Sau khi người dùng đã xác nhận yêu cầu và Planner Agent tạo `ExecutionPlan`, ba Worker Agent thực thi lần lượt các tác vụ làm sạch: loại bỏ trùng lặp, xử lý giá trị khuyết thiếu và chuẩn hóa kiểu dữ liệu. Các tác tử đều kế thừa `BaseAgent`, được đăng ký tự động bằng `@AgentRegistry.auto_register`, đọc phiên bản DataFrame mới nhất qua `physical_dataframe_path`, và ghi lại một tệp Parquet phiên bản mới. Kết quả tóm tắt được đưa vào `worker_outputs`, trạng thái chạy vào `worker_states`, và kết quả kiểm tra sơ bộ vào `validation_results` của `GlobalState`.

Thứ tự thực thi `deduplication → null_handling → type_casting` do Planner quyết định trong `task_list`. Sau mỗi worker, Validator Node kiểm tra kết quả; nếu không đạt, hệ thống có thể retry hoặc yêu cầu Planner lập kế hoạch mới. Nhờ vậy, worker chỉ thực hiện biến đổi theo một đơn giao việc đã được duyệt, thay vì tự ý thay đổi dữ liệu.

## 5.5.1 Deduplication Agent – Tác tử loại bỏ trùng lặp

Deduplication Agent xử lý các bản ghi trùng lặp theo chiến lược trong kế hoạch. Khác với hai worker còn lại, tác tử này là thành phần lai: ưu tiên quyết định đã được Planner phê duyệt, nhưng có thể gọi LLM kèm công cụ khảo sát khi kế hoạch chưa cung cấp được khóa loại trùng an toàn. Dù nguồn quyết định là gì, thao tác xóa trùng trên DataFrame luôn được thực hiện xác định bằng Pandas.

### Luồng xử lý

Khi được kích hoạt, đầu tiên Deduplication Agent truy xuất work order `deduplication` từ `execution_plan` và nạp phiên bản DataFrame mới nhất từ data lineage hoặc `physical_dataframe_path`. Tiếp theo, tác tử tổng hợp đường dẫn dữ liệu, `project_id`, hồ sơ thống kê, hồ sơ ngữ nghĩa, yêu cầu người dùng và cấu hình của Planner thành `DeduplicationAgentInput`. Trên cơ sở input này, hệ thống lựa chọn quyết định loại trùng theo thứ tự ưu tiên: tái sử dụng quyết định đã được kiểm chứng nếu ngữ cảnh không thay đổi; nếu không có thì chuyển đổi chiến lược đã được Planner phê duyệt thành quyết định thực thi; chỉ khi kế hoạch chưa đủ thông tin về khóa loại trùng, tác tử mới gọi LLM cùng các công cụ khảo sát dữ liệu. Sau đó, quyết định thu được được đối chiếu lại trên DataFrame thực tế trước khi áp dụng phép loại trùng toàn hàng (`exact_full_row`) hoặc loại trùng theo khóa (`exact_key`). DataFrame sau biến đổi được ghi thành một artifact Parquet mới và trải qua bước hậu kiểm; nếu chế độ fuzzy được bật, hệ thống chỉ sinh các cặp ứng viên trùng gần đúng kèm bằng chứng để phục vụ xem xét, không tự động hợp nhất hay xóa bản ghi. Cuối cùng, tác tử cập nhật báo cáo, nhật ký, trạng thái worker, `validation_results` và đường dẫn DataFrame hiện hành vào `GlobalState`.

### Input/Output

| Hướng | Nội dung | Định dạng |
|---|---|---|
| Input | Work order `deduplication` | `TaskDetail` trong `ExecutionPlan` |
| Input | DataFrame hiện tại | Parquet tại `physical_dataframe_path` hoặc phiên bản lineage mới nhất |
| Input | Ngữ cảnh ra quyết định | `statistical_profile`, `semantic_profile`, `user_prompt`, cấu hình fuzzy và quyết định đã cache |
| Output | DataFrame sau loại trùng | Tệp Parquet mới; cập nhật `physical_dataframe_path` |
| Output | Báo cáo loại trùng | `DeduplicationResult`: số dòng trước/sau, số dòng loại bỏ, chế độ, khóa, luật giữ dòng, trace quyết định và ghi chú |
| Output | Kiểm tra sơ bộ | `validation_results`, gồm lỗi hậu xử lý, va chạm chưa giải quyết và số ứng viên fuzzy |

### Thiết kế chi tiết

**Hai chế độ thực thi chính.** `exact_full_row` xóa các hàng giống hệt nhau trên toàn bộ cột. `exact_key` nhóm các hàng theo một hoặc nhiều khóa nghiệp vụ đã chuẩn hóa, sau đó giữ lại một bản ghi theo `keep_strategy`. Việc chuẩn hóa khóa composite giảm sai khác bề mặt của dữ liệu trước khi xác định trùng.

**Bảo vệ khóa yếu.** Agent nhận diện các khóa rủi ro, chẳng hạn chỉ dùng tên hoặc chỉ dùng số điện thoại. Khi bằng chứng ngữ nghĩa không đủ mạnh, agent không tự động gộp các bản ghi có nguy cơ khác thực thể; thay vào đó nó có thể chuyển sang loại trùng toàn dòng hoặc ghi nhận `unresolved_collisions` để Validator/HITL xử lý tiếp.

**Khớp mờ theo hướng an toàn.** Khi Planner bật fuzzy, agent chuẩn hóa văn bản, email, điện thoại và tạo các bucket ứng viên. Cấu hình gồm cột cần so sánh, khóa chặn (blocking key), cột hỗ trợ/phản bác, ngưỡng tương đồng và chính sách xử lý bucket lớn. Kết quả chỉ là tập ứng viên và bằng chứng, không phải lệnh hợp nhất tự động; điều này tránh xóa nhầm dữ liệu nhạy cảm.

**Tính tái lập.** Mỗi quyết định đã kiểm tra được gắn `context_hash`. Nếu dữ liệu và ngữ cảnh chưa đổi, agent tái sử dụng quyết định đó trong retry thay vì gọi lại LLM. Hậu kiểm bảo đảm số dòng không tăng và xác nhận trạng thái trùng sau biến đổi.

**Xử lý lỗi.** Nếu không đọc được dữ liệu, quyết định không hợp lệ, hoặc hậu kiểm thất bại, agent trả về `failed_rules` thay vì ghi nhận hoàn thành. Phiên bản lineage chỉ được Validator Node promote sau khi kiểm định toàn pipeline của tác vụ đạt.

### Thiết kế cài đặt

| Thành phần | Công nghệ/thư viện | Vai trò |
|---|---|---|
| Thực thi bảng | Pandas | Đọc/ghi Parquet, so sánh hàng, nhóm theo khóa và loại trùng xác định |
| Suy luận tùy chọn | LangChain + LLM từ `create_llm()` | Chọn chiến lược khi Planner hoặc quyết định cache chưa đủ thông tin |
| Công cụ khảo sát | LangChain tools `inspect_duplicate_candidates`, `profile_fuzzy_columns` | Cung cấp bằng chứng về nhóm trùng và cột fuzzy cho LLM |
| Schema | Pydantic v2 | Kiểm tra input, quyết định, fuzzy plan và báo cáo đầu ra |
| Điều phối/trạng thái | LangGraph `GlobalState` | Nhận work order, truyền đường dẫn phiên bản mới và cập nhật trạng thái |
| Lưu trữ | PyArrow/Parquet | Lưu artifact DataFrame sau xử lý |

Các class và hàm chính:

| Class/hàm | Vai trò |
|---|---|
| `DeduplicationAgent` | Điều phối toàn bộ luồng lựa chọn quyết định, thực thi và cập nhật state. |
| `run(state)` | Điểm vào bất đồng bộ: đọc dữ liệu, lấy/tạo quyết định, chạy loại trùng, ghi kết quả. |
| `_build_planner_owned_decision(...)` | Chuyển chiến lược đã duyệt trong Planner thành quyết định có thể thực thi. |
| `_rebuild_decision_from_state(...)` | Tái sử dụng quyết định trước đó khi `context_hash` khớp. |
| `_validate_dedup_decision(...)` | Kiểm tra khóa, mode và cấu hình trước khi biến đổi dữ liệu. |
| `execute_full_row_dedup(...)` | Xóa các hàng trùng hoàn toàn. |
| `execute_exact_key_dedup(...)` | Loại trùng theo khóa composite và luật giữ bản ghi. |
| `run_fuzzy_blocking(...)` | Sinh ứng viên fuzzy theo blocking và bằng chứng hỗ trợ. |
| `DeduplicationResult` | Schema báo cáo kết quả thực thi. |

### Prompt design

Prompt của Deduplication Agent chỉ được sử dụng ở nhánh cần LLM. `DEDUP_DECISION_SYSTEM_PROMPT` yêu cầu mô hình chọn chiến lược an toàn, gọi công cụ trước khi chọn `exact_key`, ưu tiên khóa nghiệp vụ composite thay vì khóa đơn yếu, không dùng mã kỹ thuật làm khóa nghiệp vụ khi chưa có bằng chứng, và không tự hợp nhất từ độ tương đồng fuzzy. Prompt cũng yêu cầu mô hình trả về lý do ngắn thay vì chuỗi suy luận nội bộ.

Human message được dựng động từ bối cảnh thực tế: kế hoạch Planner, thống kê null/unique, hồ sơ ngữ nghĩa, các tập khóa gợi ý và cấu hình fuzzy. `DEDUP_DECISION_JSON_INSTRUCTION` ép đầu ra JSON với các trường `mode`, `key_columns`, `column_semantics`, `fuzzy_plan`, `confidence` và `reasoning_summary`. Sau đó mã nguồn vẫn kiểm tra JSON và quyết định trên DataFrame; prompt không phải là cơ chế bảo đảm duy nhất.

## 5.5.2 Null Handling Agent – Tác tử xử lý giá trị khuyết thiếu

Null Handling Agent áp dụng chiến lược theo từng cột trong work order `null_handling`. Đây là worker xác định hoàn toàn: không khởi tạo LLM và không suy luận cách điền dữ liệu mới. Vai trò của agent là thực thi các lựa chọn đã được người dùng/Planner chốt, đồng thời chặn những phép điền không phù hợp với ngữ nghĩa cột.

### Luồng xử lý

Khi nhận được quyền thực thi, đầu tiên Null Handling Agent xác định `TaskDetail` có `task_id = null_handling` trong `ExecutionPlan` và đọc phiên bản DataFrame mới nhất. Tiếp theo, tác tử lấy cấu hình `strategy.per_column` và đối chiếu từng cột với `semantic_profile`; trong trường hợp hồ sơ này không đầy đủ, `column_context` trong work order được sử dụng làm nguồn dự phòng. Với mỗi cột thuộc phạm vi xử lý, hệ thống lần lượt xác định số lượng giá trị khuyết thực tế, kiểu dữ liệu ngữ nghĩa và thuộc tính `allow_missing`, rồi áp dụng chiến lược tương ứng hoặc điều chỉnh chiến lược về dạng an toàn hơn khi nó không phù hợp với bản chất cột. Sau đó, số ô được điền, số dòng bị loại, cột được giữ nguyên và lý do điều chỉnh được ghi nhận trong báo cáo thực thi. Cuối cùng, tác tử kiểm tra các invariant hậu xử lý, lưu DataFrame thành tệp Parquet mới và cập nhật `worker_outputs.null_agent`, `validation_results`, nhật ký hoạt động cùng trạng thái thực thi vào `GlobalState`. Vì không gọi LLM trong giai đoạn chạy, cùng một kế hoạch và cùng dữ liệu đầu vào luôn tạo ra kết quả nhất quán.

### Input/Output

| Hướng | Nội dung | Định dạng |
|---|---|---|
| Input | Work order `null_handling` | `TaskDetail.strategy.per_column` |
| Input | Hồ sơ ngữ nghĩa | `SemanticProfile`, đặc biệt `semantic_data_type`, `allow_missing`, `expected_type` |
| Input | DataFrame hiện tại | Parquet từ `physical_dataframe_path`/lineage |
| Input | Định dạng thời gian ban đầu | `original_datetime_formats` khi cần điền giá trị thời gian |
| Output | DataFrame đã xử lý null | Tệp Parquet mới tại `physical_dataframe_path` |
| Output | Báo cáo xử lý | `NullAgentResult`: số dòng trước/sau, số dòng loại bỏ, số ô điền theo cột, cột bị bỏ qua và ghi chú |
| Output | Trạng thái/kiểm tra | `worker_states`, `worker_outputs`, `agent_logs`, `ValidationResultItem` |

### Thiết kế chi tiết

**Chiến lược hỗ trợ.** Agent xử lý `drop_row`, `fill_value`, `fill_mean`, `fill_median`, `fill_mode`, `leave_as_is`/`keep_null`. Chiến lược không nhận diện được được xem là giữ nguyên và có ghi chú. `drop_column` bị chặn bởi ràng buộc hệ thống; `fill_llm` cũng bị bỏ qua để bảo toàn tính xác định và tránh tự sinh dữ liệu không được phê duyệt.

**Ràng buộc ngữ nghĩa.** Cột `Identifier` không được điền bằng thống kê: nếu không cho phép thiếu thì chuyển về `drop_row`, ngược lại giữ null. Cột `Structured text` được chuyển về giữ null hoặc xóa dòng tùy `allow_missing`. Cột `Free text`/`Geospatial` chỉ được giữ null hoặc dùng `fill_value` do người dùng chỉ định. Với `Ordinal` và `Boolean`, mean/median không phù hợp và được điều chỉnh về mode hoặc giá trị hằng. Cột liên tục có thể dùng mean/median khi hợp lệ.

**Trường hợp 100% null.** Nếu cột rỗng hoàn toàn và có `fill_value`, agent dùng giá trị đó (với cột thời gian thì cố gắng chuyển giá trị điền về kiểu temporal). Nếu không có giá trị điền mà `allow_missing = true`, null được giữ nguyên. Nếu không được phép thiếu, agent trả lỗi có chủ đích `null_ratio_100_percent_no_default` để pipeline quay về HITL/replan thay vì tự impute.

**Tính an toàn và kiểm tra.** Cột không tồn tại hoặc không có null được báo rõ trong notes. Kết quả chỉ được ghi khi `_validate_output(...)` đạt; lỗi đọc/ghi hay vi phạm hậu kiểm được chuyển thành `failed_rules` để cơ chế retry/replan xử lý.

### Thiết kế cài đặt

| Thành phần | Công nghệ/thư viện | Vai trò |
|---|---|---|
| Thực thi bảng | Pandas | Tính null, xóa dòng, điền mean/median/mode/hằng số và duy trì DataFrame |
| Schema | Pydantic v2 | `NullAgentInput`, `NullAgentResult` và contract với `TaskDetail` |
| Điều phối/trạng thái | LangGraph `GlobalState` | Cấp work order, đường dẫn artifact và lưu báo cáo worker |
| Lưu trữ | PyArrow/Parquet | Ghi phiên bản dữ liệu sau khi xử lý |
| LLM | Không sử dụng khi chạy | Bảo đảm kết quả có thể lặp lại từ cùng ExecutionPlan |

| Class/hàm | Vai trò |
|---|---|
| `NullAgent` | Worker chính thực thi work order xử lý thiếu. |
| `run(state)` | Đọc input, áp dụng chiến lược, kiểm tra, ghi artifact và cập nhật state. |
| `_extract_planner_task(...)` | Lấy tác vụ `null_handling` từ `ExecutionPlan`. |
| `_apply_null_strategies(...)` | Vòng lặp theo cột, áp dụng/điều chỉnh chiến lược theo ngữ nghĩa. |
| `_validate_output(...)` | Kiểm tra invariant sau biến đổi. |
| `NullHandlingError` | Biểu diễn lỗi có chủ đích cần validation/HITL, ví dụ cột 100% null không có default. |
| `NullAgentResult` | Schema báo cáo số ô điền, dòng loại bỏ, cột bỏ qua và đường dẫn output. |

### Prompt design

Worker này không gọi LLM, do đó không có runtime prompt. Thiết kế “prompt” được thay bằng contract dữ liệu có cấu trúc: Planner phải chuyển lựa chọn của người dùng thành `strategy.per_column`; `SemanticProfile` cung cấp ràng buộc loại cột và quyền thiếu dữ liệu. Việc đặt logic tại code thực thi giúp giới hạn không gian hành động và bảo đảm một kế hoạch giống nhau luôn tạo ra kết quả giống nhau.

## 5.5.3 Type Casting Agent – Tác tử chuẩn hóa kiểu dữ liệu

Type Casting Agent chuyển các cột về kiểu dữ liệu mục tiêu do Planner chỉ định, đồng thời ghi nhận các giá trị không thể chuyển đổi. Agent không xóa hàng, không đổi tên cột và không tác động đến cột ngoài phạm vi work order. Tương tự Null Handling Agent, việc chạy thực tế là xác định bằng Pandas.

### Luồng xử lý

Khi được kích hoạt, đầu tiên Type Casting Agent truy xuất work order `type_casting` từ `ExecutionPlan`; nếu tác vụ được đánh dấu `skip`, hệ thống kết thúc nút xử lý mà không biến đổi dữ liệu. Ngược lại, tác tử xây dựng `TypeCastingPlan` từ trường `strategy.per_column.<column>.expected_type`; khi cấu hình này chưa đầy đủ, kiểu dữ liệu đích được bổ sung từ danh sách cột trong work order và `semantic_profile`. Tiếp theo, agent đọc DataFrame hiện hành, xác nhận các cột yêu cầu đều tồn tại và kiểm tra kiểu mục tiêu thuộc tập kiểu được hỗ trợ. Với mỗi cột, hệ thống lưu lại dtype và số giá trị khuyết trước khi xử lý; riêng dữ liệu ngày và thời gian, hệ thống còn suy đoán mẫu regex và định dạng hiển thị từ giá trị mẫu để lưu vào metadata. Sau đó, quá trình ép kiểu được thực hiện trên từng Series, trong đó các giá trị không thể phân tích được được chuyển thành null và số lượng phát sinh được ghi nhận rõ ràng. Cuối cùng, sau khi kiểm tra số hàng không thay đổi, tác tử ghi DataFrame đã chuẩn hóa sang Parquet mới, đồng thời cập nhật báo cáo theo cột, `original_datetime_formats`, `validation_results` và trạng thái thực thi trong `GlobalState`.

### Input/Output

| Hướng | Nội dung | Định dạng |
|---|---|---|
| Input | Work order `type_casting` | `strategy.per_column` với `expected_type`, có thể có `parse_format` |
| Input | Hồ sơ ngữ nghĩa | `SemanticProfile.columns.<column>.expected_type` làm dự phòng |
| Input | DataFrame sau worker trước | Parquet hiện tại từ lineage/`physical_dataframe_path` |
| Output | DataFrame có dtype chuẩn hóa | Tệp Parquet mới tại `physical_dataframe_path` |
| Output | Báo cáo theo cột | `before_dtype`, `after_dtype`, null trước/sau, `coerced_nulls`, ghi chú |
| Output | Metadata ngày giờ | `original_datetime_formats` để hỗ trợ khôi phục cách hiển thị |

### Thiết kế chi tiết

**Các kiểu hỗ trợ.** `_normalize_expected_type(...)` đưa tên kiểu về sáu loại chuẩn: `int`, `float`, `str`, `bool`, `date`, `datetime`, `time`. Với số, agent chuẩn hóa biểu diễn số trước khi parse. Với boolean, agent nhận các biến thể `true/false`, `yes/no`, `y/n`, `1/0`. Với temporal, Pandas thực hiện parse và `date` được chuẩn hóa thời gian về mốc đầu ngày.

**Chuyển đổi bảo toàn dữ liệu cấu trúc.** Các giá trị null vẫn là null. Nếu một giá trị khác null không thể parse, nó được chuyển thành null và `coerced_nulls` được ghi rõ, thay vì làm hỏng toàn bộ cột hoặc xóa dòng. Nếu chuyển float sang int có thể tạo mất phần thập phân, agent thêm ghi chú để báo cáo/Validator kiểm tra tiếp.

**Nguồn chân lý và lỗi.** Planner là nguồn chân lý cho tập cột và target type. Agent không tự đoán thêm cột cần ép kiểu. Nếu kế hoạch không có đủ target type, cột yêu cầu không có trong DataFrame, target type không hỗ trợ, hay không đọc/ghi được dữ liệu, agent trả `failed_rules` để yêu cầu retry hoặc replan.

### Thiết kế cài đặt

| Thành phần | Công nghệ/thư viện | Vai trò |
|---|---|---|
| Thực thi bảng | Pandas | Ép kiểu số, chuỗi, boolean và temporal; quản lý lỗi parse bằng null |
| Cấu trúc nội bộ | `dataclass` | `TypeCastingPlan`, `TypeCastColumnResult` lưu kế hoạch và báo cáo theo cột |
| Điều phối/trạng thái | LangGraph `GlobalState` | Đọc work order, artifact hiện tại và cập nhật metadata kết quả |
| Lưu trữ | PyArrow/Parquet | Lưu DataFrame đã chuẩn hóa dtype |
| Đăng ký | `AgentRegistry` | Cho phép graph tìm và khởi tạo `TypeCastingAgent` theo tên logic |
| LLM | Không sử dụng trong `run()` | Bảo đảm chuyển đổi có tính xác định |

| Class/hàm | Vai trò |
|---|---|
| `TypeCastingAgent` | Worker điều phối chuẩn hóa dtype theo kế hoạch. |
| `run(state)` | Kiểm tra skip/plan, đọc bảng, cast từng cột, ghi output và cập nhật state. |
| `_build_casting_plan(...)` | Tổng hợp kiểu đích từ Planner, sau đó mới dùng Semantic Profile làm dự phòng. |
| `_normalize_expected_type(...)` | Chuẩn hóa tên kiểu về tập kiểu hệ thống hỗ trợ. |
| `_cast_series(...)` | Thực hiện ép kiểu một Series và trả ghi chú. |
| `_normalize_numeric_values(...)` | Làm sạch biểu diễn số trước khi parse. |
| `_parse_bool(...)` | Quy đổi các biến thể boolean về giá trị logic. |
| `_infer_datetime_format(...)` | Nhận diện format ngày/giờ từ mẫu để lưu metadata hiển thị. |
| `TypeCastColumnResult` | Báo cáo biến đổi, dtype trước/sau và số giá trị bị ép thành null. |

### Prompt design

Mã nguồn có `TYPE_AGENT_SYSTEM_PROMPT` và `TYPE_AGENT_REPLAN_GUIDANCE` như một contract mô tả vai trò Type Casting Agent: bảo toàn số hàng/tên cột, chỉ xử lý cột trong work order, hỗ trợ các target type đã định nghĩa và báo cáo mọi lỗi parse. Prompt cũng mô tả cấu trúc JSON cho báo cáo thành công/thất bại và thông tin Planner cần bổ sung khi replan.

Tuy nhiên, ở phiên bản triển khai hiện tại `TypeCastingAgent.run()` không gọi LLM; prompt không được đưa vào luồng thực thi. Cơ chế bảo đảm chính là `ExecutionPlan`, các hàm kiểm tra cột/kiểu đích và Pandas. Việc giữ prompt như một contract phục vụ tài liệu hóa, thống nhất giao diện agent và định hướng khi mở rộng agent sang chế độ LLM trong tương lai.

## 5.5.4 Tổng hợp đặc điểm triển khai của ba worker

| Đặc điểm | Deduplication Agent | Null Handling Agent | Type Casting Agent |
|---|---|---|---|
| Loại thực thi | Lai: LLM chọn quyết định khi cần, Pandas thực thi | Xác định theo work order | Xác định theo work order |
| Đơn vị biến đổi | Hàng hoặc nhóm khóa | Ô/cột và có thể là hàng | Cột |
| Có thể thay đổi số hàng | Có, khi loại trùng | Có, chỉ với `drop_row` | Không |
| Có dùng LLM runtime | Có điều kiện | Không | Không |
| Biện pháp an toàn nổi bật | Chặn khóa yếu, fuzzy chỉ sinh ứng viên | Ràng buộc ngữ nghĩa, chặn `drop_column` và `fill_llm` | Không tự đoán cột/kiểu, lỗi parse thành null có báo cáo |
| Artifact đầu ra | Parquet + `DeduplicationResult` | Parquet + `NullAgentResult` | Parquet + báo cáo `TypeCastColumnResult` theo cột |
