# Multi-stage Dockerfile for the trading-crew Python backend.
#
# Stage 1 (builder): installs uv and project dependencies into a virtual env.
# Stage 2 (runtime): copies only the venv and source; runs as a non-root user.
#
# Build:
#   docker build -t trading-crew:latest .
# Run (paper mode with a local SQLite file):
#   docker run --rm -it \
#     -v $(pwd)/data:/app/data \
#     -e DATABASE_URL=sqlite:////app/data/trading.db \
#     -e TRADING_MODE=paper \
#     trading-crew:latest

# --------------------------------------------------------------------------
# Stage 1 — builder
# --------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

# Install uv (fast Python package manager used by this project)
RUN pip install --no-cache-dir uv

# Copy dependency manifests first for layer caching
COPY pyproject.toml uv.lock* ./

# Install production dependencies (including dashboard extra for the API service)
RUN uv sync --no-dev --extra dashboard --extra notifications --no-install-project

# Copy source + readme (hatchling needs README.md for metadata) and install
COPY README.md ./
COPY src/ ./src/
RUN uv sync --no-dev --extra dashboard --extra notifications

# --------------------------------------------------------------------------
# Stage 2 — runtime
# --------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="trading-crew" \
      org.opencontainers.image.description="Multi-agent crypto trading system" \
      org.opencontainers.image.licenses="Apache-2.0"

# Create an unprivileged user; avoid running as root in production
RUN useradd --system --create-home --uid 1001 trader

WORKDIR /app

# Copy the virtual environment from the builder stage
COPY --from=builder /build/.venv /app/.venv

# Copy application source
COPY --from=builder /build/src ./src

# Copy helper scripts that may be invoked via entrypoint overrides
COPY scripts/ ./scripts/

# Volume for the SQLite database and other persistent data.
# Note: SQLite is suitable for single-instance deployments only.
# For multi-process setups switch to PostgreSQL (see docker-compose.yml).
VOLUME ["/app/data"]

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL="sqlite:////app/data/trading.db"

USER trader

ENTRYPOINT ["trading-crew"]
