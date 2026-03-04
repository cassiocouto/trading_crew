"""FastAPI dashboard application.

Serves a read-only REST API and WebSocket endpoint for the trading dashboard.
Runs as a separate process from the trading loop, sharing the same SQLite DB.

SQLite concurrency:
    WAL (Write-Ahead Logging) mode is enabled at startup so concurrent readers
    and the single trading-loop writer can coexist without SQLITE_BUSY errors.
    The engine is configured with a 5-second busy timeout.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialise shared resources on startup; clean up on shutdown."""
    from sqlalchemy import text

    from trading_crew.config.settings import get_settings
    from trading_crew.db.models import Base
    from trading_crew.db.session import get_engine
    from trading_crew.services.database_service import DatabaseService

    settings = get_settings()

    # Build a dedicated engine with SQLite timeout so we never raise SQLITE_BUSY
    engine = get_engine(settings.database_url)
    if settings.database_url.startswith("sqlite"):
        with engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.execute(text("PRAGMA busy_timeout=5000"))

    # Ensure tables exist (idempotent; prod uses alembic)
    Base.metadata.create_all(engine)

    app.state.db = DatabaseService(settings.database_url)
    app.state.ws_poll_interval = settings.dashboard_ws_poll_interval_seconds

    logger.info("Dashboard API started on %s:%d", settings.dashboard_host, settings.dashboard_port)
    yield
    logger.info("Dashboard API shutting down")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    from trading_crew.api.routers import (
        agents,
        backtest,
        cycles,
        orders,
        portfolio,
        signals,
        system,
    )
    from trading_crew.api.websocket import ws_events_handler
    from trading_crew.config.settings import get_settings

    settings = get_settings()

    app = FastAPI(
        title="Trading Crew Dashboard",
        version="0.7.0",
        description="Real-time dashboard for the Trading Crew multi-agent system.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.dashboard_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Optional API key authentication middleware
    if settings.dashboard_api_key:
        _api_key = settings.dashboard_api_key

        @app.middleware("http")
        async def api_key_middleware(request: Request, call_next: object) -> Response:
            # Pass through WebSocket upgrades and CORS pre-flights
            if request.url.path.startswith("/ws") or request.method == "OPTIONS":
                return await call_next(request)  # type: ignore[operator]
            key = request.headers.get("X-API-Key", "")
            if key != _api_key:
                return Response(content='{"detail":"Forbidden"}', status_code=403, media_type="application/json")
            return await call_next(request)  # type: ignore[operator]

    app.include_router(portfolio.router, prefix="/api/portfolio")
    app.include_router(orders.router, prefix="/api/orders")
    app.include_router(signals.router, prefix="/api/signals")
    app.include_router(cycles.router, prefix="/api/cycles")
    app.include_router(system.router, prefix="/api/system")
    app.include_router(agents.router, prefix="/api/agents")
    app.include_router(backtest.router, prefix="/api/backtest")

    app.add_api_websocket_route("/ws/events", ws_events_handler)

    return app


app = create_app()
