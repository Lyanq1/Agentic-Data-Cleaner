#import "template.typ": *
#import "@preview/codly:1.3.0": *
#import "@preview/codly-languages:0.1.1": *
#show: codly-init.with()

#show: project.with(
  title: text(19.5pt)[HƯỚNG DẪN SỬ DỤNG],
)

#set page(
  margin: (top: 2cm, bottom: 2cm, left: 2cm, right: 2cm)
)

// ================================================================
// Document Content
// ================================================================

// Cover Page

#pagebreak()

// Table of Contents
#outline(
  title: "Mục lục",
  depth: 2
)

#pagebreak()

= Điều kiện trước khi chạy

Trước khi khởi chạy hệ thống Agentic Data Cleaner, người dùng cần bảo đảm đã hoàn tất toàn bộ các bước cài đặt được trình bày trong file *`HuongDanCaiDat.txt`*. Docker Desktop phải ở trạng thái hoạt động để cung cấp hai dịch vụ PostgreSQL và Redis cho backend. Ngoài ra, file *`.env`* phải chứa API key hợp lệ của OpenAI hoặc Anthropic, đồng thời các thư viện của backend và frontend đã được cài đặt đầy đủ.

Các lệnh trong tài liệu này được thực hiện bằng PowerShell trên hệ điều hành Windows. Người dùng cần mở PowerShell tại thư mục gốc của dự án, tức thư mục chứa các file *`pyproject.toml`*, *`make.ps1`* và *`docker-compose.yml`*.

Các điều kiện cần kiểm tra trước khi chạy chương trình gồm:
- Đã hoàn tất các bước trong file *`HuongDanCaiDat.txt`*.
- Docker Desktop đang hoạt động.
- File *`.env`* đã có API key hợp lệ của OpenAI hoặc Anthropic.
- Các thư viện backend và frontend đã được cài đặt.
- Các cổng 5173, 8000, 5432 và 6379 chưa bị chương trình khác sử dụng.

= Chạy chương trình ở chế độ phát triển

Hệ thống Agentic Data Cleaner gồm ba thành phần cần được khởi động: PostgreSQL và Redis, backend FastAPI và frontend React. Các thành phần này cần được chạy trong những cửa sổ PowerShell riêng để người dùng có thể theo dõi trạng thái và log của từng dịch vụ.

== Khởi động PostgreSQL và Redis

PostgreSQL được sử dụng để lưu trạng thái checkpoint của quy trình làm sạch dữ liệu, trong khi Redis được sử dụng để quản lý phiên và hỗ trợ trao đổi trạng thái trong hệ thống. Để khởi động hai dịch vụ này, người dùng mở PowerShell tại thư mục gốc dự án và chạy lệnh:

```powershell
docker compose up -d
```

Sau khi lệnh hoàn tất, kiểm tra trạng thái các container bằng lệnh:

```powershell
docker compose ps
```

PostgreSQL và Redis cần ở trạng thái đang chạy hoặc *`healthy`* trước khi backend được khởi động. Nếu một trong hai dịch vụ không hoạt động, người dùng cần kiểm tra Docker Desktop, log của container hoặc tình trạng sử dụng các cổng mạng.

== Khởi động backend

Backend của hệ thống được xây dựng bằng FastAPI và chạy thông qua Uvicorn. Tại thư mục gốc dự án, người dùng mở một cửa sổ PowerShell riêng và chạy:

```powershell
.\make.ps1 run
```

Lệnh trên sử dụng môi trường ảo Python trong thư mục *`.venv`* và khởi động backend ở chế độ tự động nạp lại khi mã nguồn thay đổi. Trong trường hợp không sử dụng script *`make.ps1`*, có thể chạy trực tiếp Uvicorn bằng lệnh:

```powershell
.\.venv\Scripts\uvicorn.exe app.main:app --reload --host 0.0.0.0 --port 8000
```

Khi backend khởi động thành công, Uvicorn sẽ thông báo máy chủ đang lắng nghe tại địa chỉ *`http://0.0.0.0:8000`*. Người dùng có thể kiểm tra trạng thái API bằng cách truy cập:

```text
http://localhost:8000/api/v1/health
```

Kết quả mong đợi là:

```json
{"status":"ok"}
```

FastAPI tự động cung cấp giao diện tài liệu và thử nghiệm API tại địa chỉ:

```text
http://localhost:8000/docs
```

== Khởi động frontend

Sau khi PostgreSQL, Redis và backend đã hoạt động, người dùng giữ nguyên các cửa sổ PowerShell đang chạy và mở thêm một cửa sổ mới tại thư mục gốc dự án. Tiếp theo, chuyển vào thư mục *`frontend`* và khởi động Vite:

```powershell
cd frontend
npm run dev
```

Khi frontend khởi động thành công, mở trình duyệt và truy cập địa chỉ:

```text
http://localhost:5173
```

Trong thời gian sử dụng chương trình, không đóng các cửa sổ PowerShell đang chạy backend và frontend. Nếu một trong hai tiến trình bị dừng, giao diện có thể không tải được dữ liệu hoặc không thể kết nối tới API.

= Biên dịch và build chương trình

== Backend

Backend được viết bằng Python nên được thực thi theo cơ chế thông dịch và không cần biên dịch thành file thực thi trước khi chạy. Tuy nhiên, người dùng có thể kiểm tra lỗi cú pháp của toàn bộ mã nguồn trong thư mục *`app`* bằng lệnh:

```powershell
.\.venv\Scripts\python.exe -m compileall app
```

Để chạy bộ kiểm thử hiện có của dự án, sử dụng lệnh:

```powershell
.\.venv\Scripts\pytest.exe
```

Quá trình kiểm thử giúp phát hiện sớm các lỗi trong chức năng xử lý dữ liệu, API và luồng thực thi của các agent trước khi hệ thống được triển khai.

== Frontend

Frontend được xây dựng bằng React, TypeScript và Vite. Trước khi build frontend để chạy độc lập trên máy cục bộ, người dùng cần khai báo địa chỉ của backend và WebSocket. Các biến này được Vite nhúng trực tiếp vào mã frontend tại thời điểm build.

Thực hiện các lệnh sau trong PowerShell:

```powershell
cd frontend
$env:VITE_API_URL="http://localhost:8000"
$env:VITE_WS_URL="ws://localhost:8000/ws"
npm run build
```

Nếu quá trình build thành công, mã nguồn đã biên dịch được tạo trong thư mục:

```text
frontend\dist
```

Để chạy thử bản build trên cổng 5173, sử dụng lệnh:

```powershell
npm run preview -- --host 0.0.0.0 --port 5173
```

Sau đó, mở trình duyệt và truy cập *`http://localhost:5173`*.

Các biến *`VITE_API_URL`* và *`VITE_WS_URL`* được nhúng vào frontend tại thời điểm build. Do đó, nếu địa chỉ hoặc cổng của backend thay đổi, người dùng phải thiết lập lại hai biến này và thực hiện build lại frontend.

= Chạy backend bằng Docker

Ngoài phương án chạy backend trực tiếp trong môi trường ảo Python, dự án còn hỗ trợ đóng gói backend bằng Docker. Phương án này cho phép khởi động đồng thời API, PostgreSQL và Redis, giúp giảm sự khác biệt giữa các môi trường chạy.

Tại thư mục gốc dự án, chạy lệnh:

```powershell
docker compose --profile full up -d --build
```

Lệnh trên thực hiện build Docker image của backend, sau đó khởi động backend cùng PostgreSQL và Redis. Để theo dõi log của backend, sử dụng:

```powershell
docker compose logs -f api
```

Nhấn *`Ctrl+C`* để ngừng theo dõi log. Thao tác này chỉ dừng việc hiển thị log và không dừng các container đang chạy.

File *`docker-compose.yml`* hiện chỉ đóng gói backend và các dịch vụ phụ trợ, chưa đóng gói frontend. Vì vậy, sau khi backend trong Docker hoạt động, người dùng vẫn cần khởi động frontend bằng *`npm run dev`* hoặc chạy bản build frontend.

= Cách sử dụng giao diện

Sau khi toàn bộ dịch vụ đã khởi động thành công, người dùng truy cập giao diện Agentic Data Cleaner tại *`http://localhost:5173`*. Giao diện cung cấp quy trình tải dữ liệu, mô tả yêu cầu làm sạch, theo dõi hoạt động của các agent, xác nhận kế hoạch và tải kết quả sau xử lý.

Quy trình sử dụng chương trình gồm các bước sau:
- *Bước 1:* Truy cập địa chỉ *`http://localhost:5173`* bằng trình duyệt.
- *Bước 2:* Chọn chức năng tải dữ liệu lên hệ thống.
- *Bước 3:* Chọn file dữ liệu cần làm sạch. Hệ thống hỗ trợ các định dạng dữ liệu có cấu trúc như CSV, Excel và JSON.
- *Bước 4:* Nhập hoặc lựa chọn yêu cầu làm sạch dữ liệu phù hợp với tập dữ liệu.
- *Bước 5:* Theo dõi quá trình phân tích, lập kế hoạch và thực thi của các agent trên giao diện.
- *Bước 6:* Khi hệ thống yêu cầu xác nhận, xem lại kế hoạch hoặc đề xuất xử lý, sau đó chấp thuận hoặc cung cấp thông tin bổ sung.
- *Bước 7:* Sau khi tiến trình hoàn tất, xem trước dữ liệu đã làm sạch và tải file kết quả.

Người dùng không nên tải lên file có kích thước lớn hơn giới hạn *`MAX_FILE_SIZE_MB`* được cấu hình trong file *`.env`*. File đầu vào cũng cần thuộc một trong các định dạng mà hệ thống hỗ trợ để tránh lỗi trong giai đoạn phân tích dữ liệu.

= Dừng chương trình

Khi không còn sử dụng hệ thống, người dùng cần dừng các tiến trình backend, frontend và các container Docker để giải phóng tài nguyên máy tính.

Các thao tác cần thực hiện gồm:
- Tại cửa sổ PowerShell đang chạy backend, nhấn *`Ctrl+C`*.
- Tại cửa sổ PowerShell đang chạy frontend, nhấn *`Ctrl+C`*.
- Tại thư mục gốc dự án, dừng PostgreSQL và Redis bằng lệnh:

```powershell
docker compose down
```

Lệnh *`docker compose down`* dừng và xóa các container nhưng vẫn giữ dữ liệu PostgreSQL trong Docker volume. Dữ liệu này sẽ tiếp tục được sử dụng trong lần chạy sau.

Nếu hệ thống được khởi động bằng profile *`full`*, sử dụng lệnh:

```powershell
docker compose --profile full down
```

= Xử lý một số lỗi thường gặp

== Lỗi không kết nối được PostgreSQL hoặc Redis

Lỗi kết nối PostgreSQL hoặc Redis thường xảy ra khi Docker Desktop chưa được khởi động, container chưa ở trạng thái sẵn sàng hoặc cổng mạng đã bị một dịch vụ khác sử dụng.

Các bước kiểm tra gồm:
- Kiểm tra Docker Desktop đã được khởi động.
- Chạy *`docker compose ps`* để xem trạng thái các container.
- Khởi động lại các dịch vụ bằng *`docker compose up -d`*.
- Kiểm tra cổng 5432 có bị một PostgreSQL cục bộ khác sử dụng hay không.
- Kiểm tra cổng 6379 có bị một Redis cục bộ khác sử dụng hay không.

== Lỗi 401 hoặc lỗi gọi mô hình AI

Lỗi 401 thường cho biết API key không hợp lệ, đã hết hạn hoặc không có quyền truy cập mô hình được cấu hình. Người dùng cần thực hiện các bước sau:
- Kiểm tra *`OPENAI_API_KEY`* hoặc *`ANTHROPIC_API_KEY`* trong file *`.env`*.
- Kiểm tra *`DEFAULT_LLM_PROVIDER`* và *`DEFAULT_LLM_MODEL`* có phù hợp với API key hay không.
- Kiểm tra kết nối Internet của máy tính.
- Sau khi chỉnh sửa file *`.env`*, dừng và khởi động lại backend.

== Frontend không gọi được backend

Khi frontend hiển thị lỗi kết nối hoặc không tải được dữ liệu, cần kiểm tra lần lượt:
- Truy cập *`http://localhost:8000/api/v1/health`* và xác nhận API trả về *`{"status":"ok"}`*.
- Ở chế độ phát triển, mở frontend tại *`http://localhost:5173`*.
- Nếu sử dụng bản build, đặt đúng *`VITE_API_URL`* và *`VITE_WS_URL`*, sau đó build lại.
- Kiểm tra cổng 8000 không bị tường lửa hoặc phần mềm bảo mật chặn.

== PowerShell chặn chạy make.ps1 hoặc Activate.ps1

Trong một số trường hợp, chính sách thực thi của PowerShell có thể ngăn các file script hoạt động. Người dùng có thể tạm thời cho phép chạy script trong cửa sổ PowerShell hiện tại bằng lệnh:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

Thiết lập trên chỉ áp dụng cho tiến trình PowerShell hiện tại và không thay đổi vĩnh viễn chính sách của hệ thống. Sau khi thực hiện, chạy lại lệnh đã bị chặn trước đó.

== Cổng đã được sử dụng

Nếu một cổng mặc định đã bị chương trình khác sử dụng, hệ thống có thể không khởi động được hoặc frontend không thể kết nối tới backend. Các cổng mặc định của hệ thống gồm:
- Cổng 5173 dành cho frontend Vite.
- Cổng 8000 dành cho backend FastAPI.
- Cổng 5432 dành cho PostgreSQL.
- Cổng 6379 dành cho Redis.

Người dùng có thể đóng chương trình đang chiếm cổng hoặc thay đổi cổng của dịch vụ tương ứng. Khi thay đổi cổng backend, cần cập nhật *`CORS_ORIGINS`* trong file *`.env`*, đồng thời cập nhật địa chỉ API và WebSocket của frontend cho phù hợp.
