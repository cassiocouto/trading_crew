"""System status REST endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from trading_crew.api.deps import get_db
from trading_crew.api.schemas import AgentStatusResponse, SystemStatusResponse
from trading_crew.config.settings import get_settings
from trading_crew.db.models import CycleRecord
from trading_crew.db.session import get_session

if TYPE_CHECKING:
    from trading_crew.services.database_service import DatabaseService

router = APIRouter(tags=["system"])

_VERSION = "1.0.0"


@router.get("/status", response_model=SystemStatusResponse)
def get_status(db: DatabaseService = Depends(get_db)) -> SystemStatusResponse:
    """Return overall system status."""
    from sqlalchemy import func, select

    settings = get_settings()

    with get_session(db._engine) as session:
        total_cycles = int(
            session.execute(select(func.count()).select_from(CycleRecord)).scalar_one() or 0
        )
        latest_cb = session.execute(
            select(CycleRecord.circuit_breaker_tripped).order_by(CycleRecord.id.desc()).limit(1)
        ).scalar_one_or_none()
        cb_active = bool(latest_cb)

    return SystemStatusResponse(
        version=_VERSION,
        trading_mode=settings.trading_mode.value,
        advisory_enabled=settings.advisory_enabled,
        advisory_activation_threshold=settings.advisory_activation_threshold,
        total_cycles=total_cycles,
        circuit_breaker_active=cb_active,
        dashboard_ws_poll_interval_seconds=settings.dashboard_ws_poll_interval_seconds,
    )


@router.get("/agents", response_model=list[AgentStatusResponse])
def get_agents(db: DatabaseService = Depends(get_db)) -> list[AgentStatusResponse]:
    """Return advisory crew agent status (delegates to agents router)."""
    from trading_crew.api.routers.agents import get_agents as _get_agents

    return _get_agents(db)
