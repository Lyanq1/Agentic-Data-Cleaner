# Agentic Data Engineering — one-shot setup & dev shortcuts
# Chạy từ thư mục gốc repo:
#   make          → giống make setup (venv + cài đặt + .env + Docker + đợi DB)
#   make help     → danh sách lệnh

.DEFAULT_GOAL := setup

PYTHON      ?= python3.13
MIN_PYTHON  := 3.13
VENV        := .venv
PIP         := $(VENV)/bin/pip
PY          := $(VENV)/bin/python
DOCKER_COMPOSE ?= docker compose

.PHONY: help setup venv install envfile up down wait-db run uvicorn test lint fmt docker-full clean-venv

help:
	@echo "Targets:"
	@echo "  make setup      — venv + pip install -e '.[dev]' + .env + docker compose up -d + đợi DB"
	@echo "  make venv       — tạo $(VENV) với $(PYTHON) (tự tạo lại nếu sai phiên bản)"
	@echo "  make install    — nâng pip và cài package (cần venv)"
	@echo "  make envfile    — cp .env.example → .env nếu chưa có .env"
	@echo "  make up         — docker compose up -d (Postgres + Redis)"
	@echo "  make down       — docker compose down"
	@echo "  make wait-db    — sleep ngắn cho healthcheck (gọi tự động từ setup)"
	@echo "  make run        — chạy API: ade serve --reload (dùng $(VENV))"
	@echo "  make uvicorn    — uvicorn app.main:app --reload"
	@echo "  make test       — pytest tests/unit"
	@echo "  make lint       — ruff check app tests"
	@echo "  make fmt        — ruff format app tests && ruff check --fix app tests"
	@echo "  make docker-full — docker compose --profile full up -d --build (API trong Docker)"
	@echo "  make clean-venv — xoá thư mục $(VENV)"

setup: venv install envfile up wait-db
	@echo ""
	@echo "=== Setup xong ==="
	@echo "1) Mở .env và điền OPENAI_API_KEY (hoặc provider khác) nếu .env vừa được tạo."
	@echo "2) Chạy API:  make run"
	@echo "3) Kiểm tra:  curl -s http://127.0.0.1:8000/health"

venv:
	@command -v "$(PYTHON)" >/dev/null 2>&1 || { \
		echo "ERROR: $(PYTHON) không tìm thấy. Cài Python >= $(MIN_PYTHON) (vd: brew install python@3.13)"; \
		exit 1; \
	}
	@if [ -d "$(VENV)" ]; then \
		if ! "$(PY)" -c "import sys; sys.exit(0 if sys.version_info >= (3, 13) else 1)" 2>/dev/null; then \
			echo "venv: sai Python ($$("$(PY)" --version)), xoá và tạo lại với $(PYTHON)..."; \
			rm -rf "$(VENV)"; \
		fi; \
	fi
	@test -d "$(VENV)" || $(PYTHON) -m venv "$(VENV)"
	@echo "venv: $(VENV) ($$($(PY) --version))"

install: venv
	@$(PIP) install -U pip setuptools wheel
	@$(PIP) install -e ".[dev]"
	@echo "install: editable package + dev deps"

envfile:
	@test -f .env || cp .env.example .env
	@test -f .env && echo "envfile: .env ok (không ghi đè nếu đã tồn tại)"

up:
	@$(DOCKER_COMPOSE) up -d
	@echo "docker: Postgres + Redis đang chạy"

down:
	@$(DOCKER_COMPOSE) down

wait-db:
	@echo "Đợi Postgres/Redis (~12s, healthcheck)..."
	@sleep 12

run: venv
	@$(VENV)/bin/ade serve --reload

uvicorn: venv
	@$(VENV)/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test: venv
	@$(VENV)/bin/pytest tests/unit/ -v

lint: venv
	@$(VENV)/bin/ruff check app tests

fmt: venv
	@$(VENV)/bin/ruff format app tests
	@$(VENV)/bin/ruff check --fix app tests

docker-full:
	@$(DOCKER_COMPOSE) --profile full up -d --build
	@echo "docker-full: API + Postgres + Redis (cần .env với API keys)"

clean-venv:
	rm -rf "$(VENV)"
	@echo "clean-venv: đã xoá $(VENV)"
