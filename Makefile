.PHONY: install dev lint type-check test test-unit test-integration backtest format pre-commit docs clean

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

paper-trade:  ## Start in paper-trading mode (default, safe)
	TRADING_MODE=paper uv run trading-crew

live-trade:  ## Start in live-trading mode (real orders!)
	@echo "WARNING: This will place REAL orders on your exchange."
	@echo "Press Ctrl+C within 5 seconds to cancel..."
	@sleep 5
	TRADING_MODE=live uv run trading-crew

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

clean:  ## Remove build artifacts, caches, and temp files
	rm -rf dist/ build/ *.egg-info .ruff_cache/ .mypy_cache/ htmlcov/ .coverage site/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
