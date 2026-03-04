"""Agent observability REST endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from trading_crew.api.deps import get_db
from trading_crew.api.schemas import AgentStatusResponse
from trading_crew.config.settings import get_settings

if TYPE_CHECKING:
    from trading_crew.services.database_service import DatabaseService

router = APIRouter(tags=["agents"])


@router.get("/", response_model=list[AgentStatusResponse])
def get_agents(db: DatabaseService = Depends(get_db)) -> list[AgentStatusResponse]:
    """Return per-agent status derived from settings and the latest cycle record.

    Since CrewAI does not expose a cross-process tracing API, agent activity is
    inferred from the most recently completed cycle: all three agents are
    considered active when at least one cycle exists.
    """
    settings = get_settings()
    latest_cycle = db.get_latest_cycle()
    last_run_at = latest_cycle.timestamp if latest_cycle else None
    is_active = latest_cycle is not None

    return [
        AgentStatusResponse(
            name="market_intelligence",
            pipeline_mode=settings.market_pipeline_mode.value,
            last_run_at=last_run_at,
            tokens_estimated=settings.market_crew_estimated_tokens,
            is_active=is_active,
        ),
        AgentStatusResponse(
            name="strategy",
            pipeline_mode=settings.strategy_pipeline_mode.value,
            last_run_at=last_run_at,
            tokens_estimated=settings.strategy_crew_estimated_tokens,
            is_active=is_active,
        ),
        AgentStatusResponse(
            name="execution",
            pipeline_mode=settings.execution_pipeline_mode.value,
            last_run_at=last_run_at,
            tokens_estimated=settings.execution_crew_estimated_tokens,
            is_active=is_active,
        ),
    ]
