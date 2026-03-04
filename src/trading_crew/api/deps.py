"""FastAPI dependency providers for the dashboard API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request

if TYPE_CHECKING:
    from trading_crew.services.database_service import DatabaseService


def get_db(request: Request) -> DatabaseService:
    """Return the shared DatabaseService from app state."""
    return request.app.state.db  # type: ignore[no-any-return]
