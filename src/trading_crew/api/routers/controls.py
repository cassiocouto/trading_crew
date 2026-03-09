"""Runtime controls REST endpoints — toggle execution and advisory crew."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from trading_crew.api.schemas import ControlsResponse, ControlsUpdate, WsEvent
from trading_crew.api.websocket import manager
from trading_crew.config import runtime_flags
from trading_crew.config.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["controls"])


def _build_response() -> ControlsResponse:
    flags = runtime_flags.read()
    settings = get_settings()
    return ControlsResponse(
        execution_paused=flags["execution_paused"],
        advisory_paused=flags["advisory_paused"],
        advisory_available=settings.advisory_llm_configured and settings.advisory_enabled,
    )


@router.get("/", response_model=ControlsResponse)
def get_controls() -> ControlsResponse:
    """Return current runtime control flags."""
    return _build_response()


@router.patch("/", response_model=ControlsResponse)
async def update_controls(body: ControlsUpdate) -> ControlsResponse:
    """Update runtime control flags atomically.

    Rejects an unpause of the advisory crew when no LLM key is configured.
    Changes take effect on the trading bot's next cycle without a restart.
    """
    current = runtime_flags.read()
    settings = get_settings()

    # Guard: cannot unpause advisory if LLM is not configured
    if body.advisory_paused is False:
        advisory_available = settings.advisory_llm_configured and settings.advisory_enabled
        if not advisory_available:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Cannot enable advisory crew: no LLM API key is configured. "
                    "Set OPENAI_API_KEY in your .env file and restart the bot."
                ),
            )

    updated = runtime_flags.RuntimeFlags(
        execution_paused=(
            body.execution_paused
            if body.execution_paused is not None
            else current["execution_paused"]
        ),
        advisory_paused=(
            body.advisory_paused if body.advisory_paused is not None else current["advisory_paused"]
        ),
    )
    runtime_flags.write(updated)
    logger.info(
        "Runtime controls updated: execution_paused=%s, advisory_paused=%s",
        updated["execution_paused"],
        updated["advisory_paused"],
    )

    response = _build_response()

    # Broadcast to all open dashboard tabs so they refresh immediately
    await manager.broadcast(
        WsEvent(
            type="controls_updated",
            payload={
                "execution_paused": response.execution_paused,
                "advisory_paused": response.advisory_paused,
                "advisory_available": response.advisory_available,
            },
        )
    )

    return response
