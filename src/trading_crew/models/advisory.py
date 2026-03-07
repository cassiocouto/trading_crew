"""Advisory adjustment models.

The advisory crew returns **directives** (not mutated objects).  The
deterministic risk pipeline then re-derives OrderRequests from the adjusted
signals, keeping advisory pure and avoiding portfolio desync.
"""

from __future__ import annotations

import logging
from enum import StrEnum

from pydantic import BaseModel, Field

from trading_crew.models.signal import SignalType, TradeSignal

logger = logging.getLogger(__name__)


class AdjustmentAction(StrEnum):
    """Actions the advisory crew may recommend."""

    VETO_SIGNAL = "veto_signal"
    ADJUST_CONFIDENCE = "adjust_confidence"
    TIGHTEN_STOP_LOSS = "tighten_stop_loss"
    REDUCE_POSITION_SIZE = "reduce_position_size"
    SIT_OUT = "sit_out"


class AdvisoryAdjustment(BaseModel, frozen=True):
    """A single advisory directive.

    ``symbol`` is None for SIT_OUT (affects the entire cycle).
    ``params`` carries action-specific numeric values, e.g.
    ``{"new_confidence": 0.4}`` or ``{"stop_loss_pct": 0.02}``.
    """

    action: AdjustmentAction
    symbol: str | None = None
    reason: str
    params: dict[str, float] = Field(default_factory=dict)


class AdvisoryResult(BaseModel):
    """Output of the advisory crew for one cycle."""

    adjustments: list[AdvisoryAdjustment] = Field(default_factory=list)
    summary: str = ""
    uncertainty_score: float = 0.0


def apply_advisory_directives(
    signals: list[TradeSignal],
    result: AdvisoryResult,
) -> list[TradeSignal]:
    """Apply advisory directives to a list of trade signals.

    Returns a new list of ``TradeSignal``s (original objects are frozen).
    The caller should re-run the risk pipeline on the returned signals to
    re-derive order requests with correct position sizing.
    """
    if any(a.action == AdjustmentAction.SIT_OUT for a in result.adjustments):
        return []

    veto_symbols: set[str] = {
        a.symbol
        for a in result.adjustments
        if a.action == AdjustmentAction.VETO_SIGNAL and a.symbol is not None
    }

    confidence_overrides: dict[str, float] = {}
    for adj in result.adjustments:
        if adj.action == AdjustmentAction.ADJUST_CONFIDENCE and adj.symbol is not None:
            new_conf = adj.params.get("new_confidence")
            if new_conf is not None:
                confidence_overrides[adj.symbol] = max(0.0, min(1.0, new_conf))

    stop_loss_overrides: dict[str, float] = {}
    for adj in result.adjustments:
        if adj.action == AdjustmentAction.TIGHTEN_STOP_LOSS and adj.symbol is not None:
            sl_pct = adj.params.get("stop_loss_pct")
            if sl_pct is not None:
                stop_loss_overrides[adj.symbol] = sl_pct

    size_multipliers: dict[str, float] = {}
    for adj in result.adjustments:
        if adj.action == AdjustmentAction.REDUCE_POSITION_SIZE and adj.symbol is not None:
            factor = adj.params.get("size_factor")
            if factor is not None:
                size_multipliers[adj.symbol] = max(0.01, min(1.0, factor))
            else:
                logger.warning(
                    "REDUCE_POSITION_SIZE for %s missing 'size_factor' param; ignoring",
                    adj.symbol,
                )

    for adj in result.adjustments:
        if adj.action not in {
            AdjustmentAction.VETO_SIGNAL,
            AdjustmentAction.ADJUST_CONFIDENCE,
            AdjustmentAction.TIGHTEN_STOP_LOSS,
            AdjustmentAction.REDUCE_POSITION_SIZE,
            AdjustmentAction.SIT_OUT,
        }:
            logger.warning("Unhandled advisory action: %s", adj.action)

    adjusted: list[TradeSignal] = []
    for sig in signals:
        if sig.symbol in veto_symbols:
            continue
        updates: dict[str, object] = {}
        if sig.symbol in confidence_overrides:
            updates["confidence"] = confidence_overrides[sig.symbol]
        if sig.symbol in stop_loss_overrides:
            pct = max(0.001, min(0.5, stop_loss_overrides[sig.symbol]))
            if sig.signal_type == SignalType.SELL:
                updates["stop_loss_price"] = sig.entry_price * (1.0 + pct)
            else:
                updates["stop_loss_price"] = sig.entry_price * (1.0 - pct)
        if sig.symbol in size_multipliers:
            updates["confidence"] = sig.confidence * size_multipliers[sig.symbol]
        if updates:
            adjusted.append(sig.model_copy(update=updates))
        else:
            adjusted.append(sig)

    return adjusted
