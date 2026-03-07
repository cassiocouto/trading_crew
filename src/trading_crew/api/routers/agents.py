"""Agent observability REST endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from trading_crew.api.deps import get_db
from trading_crew.api.schemas import AgentStatusResponse
from trading_crew.config.settings import get_settings
from trading_crew.db.models import CycleRecord
from trading_crew.db.session import get_session

if TYPE_CHECKING:
    from trading_crew.services.database_service import DatabaseService

router = APIRouter(tags=["agents"])


@router.get("/", response_model=list[AgentStatusResponse])
def get_agents(db: DatabaseService = Depends(get_db)) -> list[AgentStatusResponse]:
    """Return advisory crew status.

    Since CrewAI does not expose a cross-process tracing API, agent activity is
    inferred from cycle records where ``advisory_ran`` is True.
    """
    from datetime import UTC, datetime

    from sqlalchemy import func, select

    settings = get_settings()
    latest_cycle = db.get_latest_cycle()
    last_run_at = latest_cycle.timestamp if latest_cycle else None
    is_active = settings.advisory_enabled and bool(settings.openai_api_key)

    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    with get_session(db._engine) as session:
        activations_today = int(
            session.execute(
                select(func.count())
                .select_from(CycleRecord)
                .where(CycleRecord.advisory_ran.is_(True))
                .where(CycleRecord.timestamp >= today_start)
            ).scalar_one()
            or 0
        )

    return [
        AgentStatusResponse(
            name="advisory_crew",
            role="Condition-triggered advisory",
            last_run_at=last_run_at,
            advisory_activations_today=activations_today,
            is_active=is_active,
        ),
    ]
