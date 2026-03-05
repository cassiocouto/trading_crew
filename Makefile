.PHONY: install dev lint type-check test test-unit test-integration backtest backtest-run backtest-data format pre-commit docs clean dashboard-api dashboard-ui dashboard-install docker-build docker-up docker-down

# ---------------------------------------------------------------------------
# Cross-platform date helpers (Python works on Windows, macOS, and Linux)
# ---------------------------------------------------------------------------
NINETY_DAYS_AGO := $(shell python -c "from datetime import date,timedelta;print(date.today()-timedelta(days=90))")
TODAY := $(shell python -c "from datetime import date;print(date.today())")

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

install:  ## Install production dependencies
	uv sync

dev:  ## Install all dependencies (dev + docs + notifications)
	uv sync --all-extras
	uv run pre-commit install

# ---------------------------------------------------------------------------
# Code Quality
# ---------------------------------------------------------------------------

lint:  ## Run linter (ruff)
	uv run ruff check src/ tests/

format:  ## Auto-format code
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

type-check:  ## Run type checker (mypy)
	uv run mypy src/

pre-commit:  ## Run all pre-commit hooks
	uv run pre-commit run --all-files

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------

test:  ## Run all tests
	uv run pytest

test-unit:  ## Run unit tests only
	uv run pytest -m unit

test-integration:  ## Run integration tests only
	uv run pytest -m integration

backtest:  ## Run backtesting tests
	uv run pytest -m backtest

backtest-run:  ## Run backtest script (BTC/USDT 1h, last 90 days)
	uv run python scripts/backtest_runner.py \
		--symbol BTC/USDT --exchange binance --timeframe 1h \
		--from-date $(NINETY_DAYS_AGO) \
		--to-date $(TODAY) \
		--compare

backtest-data:  ## Fetch and cache OHLCV data only (no backtest run)
	uv run python scripts/backtest_runner.py \
		--symbol BTC/USDT --exchange binance --timeframe 1h \
		--from-date $(NINETY_DAYS_AGO) \
		--to-date $(TODAY) \
		--fetch --data-only

test-cov:  ## Run tests with coverage report
	uv run pytest --cov=trading_crew --cov-report=html --cov-report=term-missing

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

db-migrate:  ## Create a new migration (usage: make db-migrate msg="add orders table")
	uv run alembic revision --autogenerate -m "$(msg)"

db-upgrade:  ## Apply all pending migrations
	uv run alembic upgrade head

db-downgrade:  ## Roll back last migration
	uv run alembic downgrade -1

# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------

ifeq ($(OS),Windows_NT)
paper-trade:  ## Start in paper-trading mode (default, safe)
	set "TRADING_MODE=paper" && uv run trading-crew

live-trade:  ## Start in live-trading mode (real orders!)
	@echo WARNING: This will place REAL orders on your exchange.
	@echo Press Ctrl+C within 5 seconds to cancel...
	@python -c "import time; time.sleep(5)"
	set "TRADING_MODE=live" && uv run trading-crew
else
paper-trade:  ## Start in paper-trading mode (default, safe)
	TRADING_MODE=paper uv run trading-crew

live-trade:  ## Start in live-trading mode (real orders!)
	@echo "WARNING: This will place REAL orders on your exchange."
	@echo "Press Ctrl+C within 5 seconds to cancel..."
	@sleep 5
	TRADING_MODE=live uv run trading-crew
endif

# ---------------------------------------------------------------------------
# Documentation
# ---------------------------------------------------------------------------

docs:  ## Build documentation site
	uv run mkdocs build

docs-serve:  ## Serve docs locally with hot reload
	uv run mkdocs serve

# ---------------------------------------------------------------------------
# Housekeeping
# ---------------------------------------------------------------------------

ifeq ($(OS),Windows_NT)
clean:  ## Remove build artifacts, caches, and temp files
	if exist dist rmdir /s /q dist
	if exist build rmdir /s /q build
	if exist .ruff_cache rmdir /s /q .ruff_cache
	if exist .mypy_cache rmdir /s /q .mypy_cache
	if exist htmlcov rmdir /s /q htmlcov
	if exist site rmdir /s /q site
	if exist .coverage del .coverage
	python -c "import shutil,pathlib;[shutil.rmtree(p) for p in pathlib.Path('.').rglob('__pycache__')]"
else
clean:  ## Remove build artifacts, caches, and temp files
	rm -rf dist/ build/ *.egg-info .ruff_cache/ .mypy_cache/ htmlcov/ .coverage site/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
endif

# ---------------------------------------------------------------------------
# Dashboard (Phase 7)
# ---------------------------------------------------------------------------

dashboard-install:  ## Install dashboard Python + Node deps
	uv sync --extra dashboard
	cd dashboard && npm install

dashboard-api:  ## Start FastAPI dashboard server (port 8000)
	uv run python scripts/dashboard.py

dashboard-ui:  ## Start Next.js dev server (port 3000, requires Node)
	cd dashboard && npm run dev

# ---------------------------------------------------------------------------
# Docker (Phase 8)
# ---------------------------------------------------------------------------

docker-build:  ## Build all Docker images (backend + dashboard)
	docker compose build

ifeq ($(OS),Windows_NT)
docker-up:  ## Start all services in detached mode
	if not exist data mkdir data
	docker compose up --build -d
else
docker-up:  ## Start all services in detached mode
	mkdir -p data
	docker compose up --build -d
endif

docker-down:  ## Stop and remove all containers (data volume preserved)
	docker compose down

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
