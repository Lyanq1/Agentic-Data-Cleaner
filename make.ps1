param(
    [Parameter(Position = 0)]
    [string]$Target = "setup"
)
$ErrorActionPreference = "Stop"
# Configuration
$PYTHON = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$VENV = ".venv"
$PIP = "$VENV\Scripts\pip.exe"
$PY = "$VENV\Scripts\python.exe"
$VENV_BIN = "$VENV\Scripts"
$DOCKER_COMPOSE = if ($env:DOCKER_COMPOSE) { $env:DOCKER_COMPOSE } else { "docker compose" }
# Functions (targets)
function Show-Help {
    Write-Host "Targets:"
    Write-Host "  .\make.ps1 setup       - Create venv, install deps, copy .env, start db services"
    Write-Host "  .\make.ps1 venv        - Create virtual environment ($VENV) if it does not exist"
    Write-Host "  .\make.ps1 install     - Upgrade pip and install package in editable mode"
    Write-Host "  .\make.ps1 envfile     - Copy .env.example to .env if .env does not exist"
    Write-Host "  .\make.ps1 up          - Run docker compose up -d (Postgres + Redis)"
    Write-Host "  .\make.ps1 down        - Run docker compose down"
    Write-Host "  .\make.ps1 wait-db     - Sleep briefly for healthcheck (called automatically by setup)"
    Write-Host "  .\make.ps1 run         - Run the API server using uvicorn"
    Write-Host "  .\make.ps1 test        - Run pytest on tests/unit"
    Write-Host "  .\make.ps1 lint        - Run ruff check on src and tests"
    Write-Host "  .\make.ps1 fmt         - Run ruff format and fix on src and tests"
    Write-Host "  .\make.ps1 docker-full - Run docker compose --profile full up -d --build (API in Docker)"
    Write-Host "  .\make.ps1 clean-venv  - Remove the virtual environment directory ($VENV)"
}
function Do-Venv {
    if (-not (Test-Path $VENV)) {
        & $PYTHON -m venv $VENV
        if ($LASTEXITCODE -ne 0) { throw "Failed to create venv" }
    }
    Write-Host "venv: $VENV ready"
}
function Do-Install {
    Do-Venv
    Write-Host "Upgrading pip/setuptools/wheel..."
    & $PY -m pip install -U pip setuptools wheel
    if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade pip" }
    Write-Host "Installing project (editable + dev)..."
    & $PY -m pip install -e ".[dev]"
    if ($LASTEXITCODE -ne 0) { throw "Failed to install package" }
    Write-Host "install: done"
}
function Do-Envfile {
    if (-not (Test-Path .env)) {
        Copy-Item .env.example .env
        Write-Host "envfile: created .env from .env.example"
    } else {
        Write-Host "envfile: .env already exists (not overwriting)"
    }
}
function Do-Up {
    Invoke-Expression "$DOCKER_COMPOSE up -d"
    if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }
    Write-Host "docker: Postgres and Redis are running"
}
function Do-Down {
    Invoke-Expression "$DOCKER_COMPOSE down"
}
function Do-WaitDb {
    Write-Host "Waiting for Postgres/Redis healthchecks (12s)..."
    Start-Sleep -Seconds 12
}
function Do-Run {
    Do-Venv
    & "$VENV_BIN\uvicorn" app.main:app --reload --host 0.0.0.0 --port 8000
}
function Do-Test {
    Do-Venv
    & "$VENV_BIN\pytest" tests/unit/ -v
}
function Do-Lint {
    Do-Venv
    & "$VENV_BIN\ruff" check src tests
}
function Do-Fmt {
    Do-Venv
    & "$VENV_BIN\ruff" format src tests
    & "$VENV_BIN\ruff" check --fix src tests
}
function Do-DockerFull {
    Invoke-Expression "$DOCKER_COMPOSE --profile full up -d --build"
    if ($LASTEXITCODE -ne 0) { throw "docker compose full failed" }
    Write-Host "docker-full: API, Postgres, and Redis are running (requires .env with API keys)"
}
function Do-CleanVenv {
    if (Test-Path $VENV) {
        Remove-Item -Recurse -Force $VENV
    }
    Write-Host "clean-venv: removed $VENV"
}
function Do-Setup {
    Do-Venv
    Do-Install
    Do-Envfile
    Do-Up
    Do-WaitDb
    Write-Host ""
    Write-Host "=== Setup completed ==="
    Write-Host "1) Open .env and fill in OPENAI_API_KEY (or other provider) if it was just created."
    Write-Host "2) Run API:  .\make.ps1 run"
    Write-Host "3) Check:    curl -s http://127.0.0.1:8000/health"
}
# Dispatcher
switch ($Target.ToLower()) {
    "help"        { Show-Help }
    "setup"       { Do-Setup }
    "venv"        { Do-Venv }
    "install"     { Do-Install }
    "envfile"     { Do-Envfile }
    "up"          { Do-Up }
    "down"        { Do-Down }
    "wait-db"     { Do-WaitDb }
    "run"         { Do-Run }
    "test"        { Do-Test }
    "lint"        { Do-Lint }
    "fmt"         { Do-Fmt }
    "docker-full" { Do-DockerFull }
    "clean-venv"  { Do-CleanVenv }
    default {
        Write-Host "Error: invalid target '$Target'" -ForegroundColor Red
        Write-Host ""
        Show-Help
        exit 1
    }
}
