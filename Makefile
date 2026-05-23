# Agentic Data Engineering — one-shot setup & dev shortcuts
# Chạy từ thư mục gốc repo:
#   make          → giống make setup (venv + cài đặt + .env + Docker + đợi DB)
#   make help     → danh sách lệnh

.DEFAULT_GOAL := setup

PYTHON      ?= python3.11
VENV        := .venv
PIP         := $(VENV)/bin/pip
PY          := $(VENV)/bin/python
DOCKER_COMPOSE ?= docker compose

.PHONY: help setup venv install envfile up down wait-db run uvicorn test lint fmt docker-full clean-venv

help:
	@echo "Targets:"
	@echo "  make setup      — venv + pip install -e '.[dev]' + .env + docker compose up -d + đợi DB"
	@echo "  make venv       — tạo $(VENV) nếu chưa có"
	@echo "  make install    — nâng pip và cài package (cần venv)"
	@echo "  make envfile    — cp .env.example → .env nếu chưa có .env"
	@echo "  make up         — docker compose up -d (Postgres + Redis)"
	@echo "  make down       — docker compose down"
	@echo "  make wait-db    — sleep ngắn cho healthcheck (gọi tự động từ setup)"
	@echo "  make run        — chạy API: ade serve --reload (dùng $(VENV))"
	@echo "  make uvicorn    — uvicorn src.api.main:app --reload"
	@echo "  make test       — pytest tests/unit"
	@echo "  make lint       — ruff check src tests"
	@echo "  make fmt        — ruff format src tests && ruff check --fix src tests"
	@echo "  make docker-full — docker compose --profile full up -d --build (API trong Docker)"
	@echo "  make clean-venv — xoá thư mục $(VENV)"

setup: venv install envfile up wait-db
	@echo ""
	@echo "=== Setup xong ==="
	@echo "1) Mở .env và điền OPENAI_API_KEY (hoặc provider khác) nếu .env vừa được tạo."
	@echo "2) Chạy API:  make run"
	@echo "3) Kiểm tra:  curl -s http://127.0.0.1:8000/health"

venv:
	@test -d "$(VENV)" || $(PYTHON) -m venv "$(VENV)"
	@echo "venv: $(VENV)"

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
	@$(VENV)/bin/uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

test: venv
	@$(VENV)/bin/pytest tests/unit/ -v

lint: venv
	@$(VENV)/bin/ruff check src tests

fmt: venv
	@$(VENV)/bin/ruff format src tests
	@$(VENV)/bin/ruff check --fix src tests

docker-full:
	@$(DOCKER_COMPOSE) --profile full up -d --build
	@echo "docker-full: API + Postgres + Redis (cần .env với API keys)"

clean-venv:
	rm -rf "$(VENV)"
	@echo "clean-venv: đã xoá $(VENV)"
