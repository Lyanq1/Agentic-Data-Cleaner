#import "template.typ": *
#import "@preview/codly:1.3.0": *
#import "@preview/codly-languages:0.1.1": *
#show: codly-init.with()

#show: project.with(
  title: text(19.5pt)[HƯỚNG DẪN CÀI ĐẶT],
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

= Giới thiệu

Agentic Data Cleaner là hệ thống hỗ trợ làm sạch dữ liệu có cấu trúc bằng kiến trúc đa tác tử. Hệ thống tiếp nhận tập dữ liệu, phân tích các vấn đề chất lượng, xây dựng kế hoạch xử lý và thực hiện những tác vụ như loại bỏ dữ liệu trùng lặp, xử lý giá trị khuyết thiếu và chuyển đổi kiểu dữ liệu.

Kiến trúc của hệ thống gồm các thành phần chính sau:
- *Backend:* được xây dựng bằng Python, FastAPI, LangGraph và LangChain, chịu trách nhiệm cung cấp API và điều phối quy trình làm sạch dữ liệu.
- *Frontend:* được xây dựng bằng React, TypeScript, Vite và Tailwind CSS, cung cấp giao diện tương tác cho người dùng.
- *Cơ sở dữ liệu:* PostgreSQL 16 được sử dụng để lưu trạng thái checkpoint của quy trình xử lý.
- *Bộ nhớ đệm và lưu phiên:* Redis 7 được sử dụng để quản lý trạng thái phiên và hỗ trợ trao đổi dữ liệu trong hệ thống.
- *Mô hình ngôn ngữ:* hệ thống hỗ trợ OpenAI hoặc Anthropic và yêu cầu API key tương ứng.

Tài liệu này ưu tiên cách cài đặt trên Windows 10 hoặc Windows 11 bằng PowerShell. Người dùng Linux và macOS có thể tham khảo phần hướng dẫn ở cuối tài liệu.

= Công cụ và môi trường cần thiết

Trước khi cài đặt mã nguồn, người dùng cần chuẩn bị các công cụ phục vụ việc chạy backend, frontend và các dịch vụ phụ trợ. Các công cụ phải đáp ứng phiên bản tối thiểu mà dự án yêu cầu để tránh lỗi không tương thích thư viện.

== Công cụ bắt buộc

Các công cụ bắt buộc gồm:
- *Python 3.13 trở lên:* dự án khai báo *`requires-python >= 3.13`* trong file *`pyproject.toml`*.
- *Node.js:* sử dụng phiên bản 20.19 trở lên hoặc 22.12 trở lên. Khuyến nghị sử dụng Node.js 24.x.
- *npm:* được cài đặt kèm theo Node.js và dùng để quản lý thư viện frontend.
- *Docker Desktop:* phải hỗ trợ lệnh *`docker compose`* để chạy PostgreSQL và Redis.
- *Kết nối Internet:* cần thiết trong lần đầu tải thư viện Python, package npm và Docker image.

== Công cụ khuyến nghị

Ngoài các công cụ bắt buộc, người dùng nên cài đặt:
- *Git:* dùng để tải, cập nhật và quản lý phiên bản mã nguồn.
- *Visual Studio Code hoặc PyCharm:* dùng để xem và chỉnh sửa mã nguồn.
- *Chrome, Edge hoặc Firefox:* dùng để truy cập và kiểm thử giao diện web.

== Kiểm tra công cụ

Mở PowerShell và chạy lần lượt các lệnh sau:

```powershell
python --version
node --version
npm --version
docker --version
docker compose version
```

#align(center)[
  #image("env_overall_check.png", scaling: auto)
]

Mỗi lệnh phải hiển thị phiên bản của công cụ tương ứng. Nếu PowerShell thông báo không nhận diện được lệnh, người dùng cần cài đặt lại công cụ, kiểm tra biến môi trường *`PATH`* và mở một cửa sổ PowerShell mới.

Docker Desktop phải được khởi động hoàn toàn trước khi chạy các lệnh Docker Compose. Có thể kiểm tra nhanh bằng lệnh *`docker info`*.

= Các thư viện chính

Các thư viện backend được khai báo trong file *`pyproject.toml`*, còn thư viện frontend được khai báo trong *`frontend/package.json`* và khóa phiên bản trong *`frontend/package-lock.json`*. Người dùng không cần cài đặt riêng lẻ từng thư viện vì trình quản lý package sẽ thực hiện tự động.

== Thư viện backend

Các nhóm thư viện backend chính gồm:
- *Xử lý dữ liệu:* pandas, NumPy, PyArrow và openpyxl.
- *Trí tuệ nhân tạo và agent:* LangGraph, LangChain, langchain-openai và langchain-anthropic.
- *Web API:* FastAPI, Uvicorn, WebSockets và python-multipart.
- *Lưu trữ dữ liệu:* PostgreSQL, Psycopg, SQLAlchemy và Redis.
- *Cấu hình và kiểm thử:* Pydantic, pydantic-settings, pytest, Ruff và mypy.

== Thư viện frontend

Các nhóm thư viện frontend chính gồm:
- React 19, React DOM, TypeScript và Vite 8.
- Tailwind CSS để xây dựng giao diện.
- Axios và TanStack React Query để giao tiếp và quản lý dữ liệu từ API.
- PapaParse và xlsx để hỗ trợ đọc dữ liệu CSV và Excel.

= Cài đặt trên Windows

== Mở thư mục dự án

Sau khi giải nén hoặc sao chép mã nguồn, người dùng mở PowerShell tại thư mục gốc của dự án. Đây là thư mục chứa các file *`pyproject.toml`*, *`make.ps1`* và *`docker-compose.yml`*.

Ví dụ:

```powershell
cd "C:\duong-dan\Agentic-Data-Cleaner"
```

Tất cả các lệnh cài đặt backend và Docker trong những phần tiếp theo cần được thực hiện từ thư mục này.

== Tạo file cấu hình môi trường

Các biến cấu hình và thông tin xác thực được lưu trong file *`.env`*. Nếu thư mục dự án chưa có file này, tạo file *`.env`* từ mẫu bằng lệnh:

```powershell
Copy-Item .env.example .env
```

Nếu file *`.env`* đã tồn tại, không chạy lại lệnh trên để tránh ghi đè cấu hình hiện có.

Mở file *`.env`* bằng trình soạn thảo và cấu hình nhà cung cấp mô hình ngôn ngữ. Khi sử dụng OpenAI, thiết lập:

```text
OPENAI_API_KEY=<API_KEY_CUA_BAN>
DEFAULT_LLM_PROVIDER=openai
DEFAULT_LLM_MODEL=gpt-4o
```

Khi sử dụng Anthropic, thiết lập:

```text
ANTHROPIC_API_KEY=<API_KEY_CUA_BAN>
DEFAULT_LLM_PROVIDER=anthropic
DEFAULT_LLM_MODEL=<TEN_MODEL_ANTHROPIC>
```

Nếu không sử dụng LangSmith để theo dõi hoạt động của mô hình, nên cấu hình:

```text
LANGCHAIN_TRACING_V2=false
LANGCHAIN_API_KEY=
```

Khi backend được chạy trực tiếp trên Windows và PostgreSQL, Redis được chạy bằng Docker, giữ nguyên các địa chỉ dịch vụ cục bộ:

```text
POSTGRES_URL=postgresql://user:password@localhost:5432/agentic_data_cleaner_db
REDIS_URL=redis://localhost:6379/0
```

File *`.env`* chứa API key và thông tin cấu hình nhạy cảm. Không chia sẻ file này, không đưa API key vào báo cáo và không tải file lên kho mã nguồn công khai.

== Cài backend và khởi động PostgreSQL, Redis tự động

Dự án cung cấp script *`make.ps1`* để tự động tạo môi trường ảo, cài thư viện backend và khởi động các dịch vụ Docker. Tại thư mục gốc dự án, chạy:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\make.ps1 setup
```

Lệnh *`Set-ExecutionPolicy`* chỉ cho phép chạy script trong cửa sổ PowerShell hiện tại. Lệnh *`.\make.ps1 setup`* thực hiện các công việc sau:
- Tạo môi trường ảo Python tại thư mục *`.venv`*.
- Nâng cấp pip, setuptools và wheel.
- Cài package backend cùng các thư viện phát triển.
- Tạo file *`.env`* từ *`.env.example`* nếu file *`.env`* chưa tồn tại.
- Tải và chạy PostgreSQL 16 cùng Redis 7 bằng Docker Compose.
- Chờ các dịch vụ phụ trợ hoàn tất quá trình khởi động.

Sau khi lệnh hoàn tất, người dùng cần kiểm tra lại file *`.env`* và bảo đảm API key đã được khai báo chính xác.

== Cài frontend

Tại thư mục gốc dự án, chuyển vào thư mục *`frontend`*, cài package và quay lại thư mục gốc:

```powershell
cd frontend
npm ci
cd ..
```

Nên sử dụng *`npm ci`* thay cho *`npm install`* để cài đặt đúng các phiên bản đã được khóa trong file *`package-lock.json`*. Cách này giúp môi trường chạy giữa các máy có tính nhất quán cao hơn.

= Cài đặt thủ công

Trong trường hợp không sử dụng được script *`make.ps1`*, người dùng có thể thực hiện từng bước cài đặt thủ công. Tại thư mục gốc dự án, chạy lần lượt:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
docker compose up -d
cd frontend
npm ci
cd ..
```

Ý nghĩa của các lệnh trên:
- *`python -m venv .venv`* tạo môi trường ảo Python riêng cho dự án.
- *`.\.venv\Scripts\Activate.ps1`* kích hoạt môi trường ảo trong PowerShell.
- *`python -m pip install --upgrade pip setuptools wheel`* cập nhật công cụ cài package Python.
- *`python -m pip install -e ".[dev]"`* cài backend và các thư viện phát triển ở chế độ editable.
- *`docker compose up -d`* khởi động PostgreSQL và Redis ở chế độ nền.
- *`npm ci`* cài đặt các thư viện frontend theo file khóa phiên bản.

Nếu file *`.env`* đã tồn tại, bỏ qua lệnh *`Copy-Item .env.example .env`* để không ghi đè API key và các giá trị cấu hình hiện có.

= Cài đặt backend hoàn toàn bằng Docker

Ngoài cách chạy backend trong môi trường ảo Python, dự án hỗ trợ build và chạy backend bằng Docker. Sau khi đã tạo và điền đầy đủ file *`.env`*, chạy tại thư mục gốc:

```powershell
docker compose --profile full up -d --build
```

Lệnh này build Docker image của backend và khởi động đồng thời API, PostgreSQL và Redis. Cách cài đặt này hạn chế sự khác biệt về thư viện Python giữa các máy.

Frontend hiện chưa được đóng gói trong file *`docker-compose.yml`*. Vì vậy, người dùng vẫn phải cài đặt frontend bằng *`npm ci`* và chạy frontend bằng npm.

= Kiểm tra sau khi cài đặt

Sau khi hoàn tất quá trình cài đặt, người dùng nên kiểm tra lần lượt các thành phần trước khi chạy toàn bộ chương trình.

== Kiểm tra dịch vụ Docker

Chạy lệnh:

```powershell
docker compose ps
```

PostgreSQL và Redis phải ở trạng thái đang chạy hoặc *`healthy`*. Nếu container không hoạt động, có thể kiểm tra log bằng:

```powershell
docker compose logs postgres
docker compose logs redis
```

== Kiểm tra thư viện backend

Chạy lệnh sau tại thư mục gốc dự án:

```powershell
.\.venv\Scripts\python.exe -c "import fastapi, langgraph, pandas, redis; print('Backend OK')"
```

Nếu PowerShell hiển thị *`Backend OK`* và không có lỗi import, các thư viện backend chính đã được cài đặt thành công.

== Kiểm tra khả năng build frontend

Chạy lần lượt:

```powershell
cd frontend
npm run build
cd ..
```

Nếu lệnh không báo lỗi và thư mục *`frontend/dist`* được tạo, frontend đã được cài đặt đúng và có thể build thành công.

= Các cổng mặc định

Các thành phần của hệ thống sử dụng những cổng mặc định sau:
- *Frontend Vite:* cổng 5173.
- *Backend FastAPI:* cổng 8000.
- *PostgreSQL:* cổng 5432.
- *Redis:* cổng 6379.

Nếu một trong các cổng trên đã bị chương trình khác sử dụng, dịch vụ tương ứng có thể không khởi động được. Người dùng cần dừng chương trình đang chiếm cổng hoặc thay đổi cấu hình cổng trong dự án. Khi thay đổi cổng backend, cần cập nhật cấu hình CORS và địa chỉ API của frontend cho phù hợp.

= Cài đặt trên Linux và macOS

Trên Linux hoặc macOS, yêu cầu về phiên bản Python, Node.js, npm và Docker tương tự như trên Windows. Tại thư mục gốc dự án, chạy:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
cp .env.example .env
docker compose up -d
cd frontend
npm ci
cd ..
```

Sau khi các lệnh hoàn tất, mở file *`.env`* và cấu hình API key, nhà cung cấp mô hình, PostgreSQL và Redis tương tự phần hướng dẫn cài đặt trên Windows.

Để kiểm tra backend trên Linux hoặc macOS, sử dụng:

```bash
.venv/bin/python -c "import fastapi, langgraph, pandas, redis; print('Backend OK')"
```

Khi quá trình cài đặt và kiểm tra hoàn tất, người dùng thực hiện các bước trong tài liệu hướng dẫn sử dụng để khởi động và vận hành hệ thống.
