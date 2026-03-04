"""Position sizing algorithms.

Determines how much capital to allocate to a single trade based on risk
parameters and portfolio state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from trading_crew.models.portfolio import Portfolio
    from trading_crew.models.risk import RiskParams

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PositionSizeResult:
    """Result of position size calculation.

    Attributes:
        value: Final capped position size in quote currency.
        risk_based_value: Uncapped size derived purely from risk-per-trade.
        was_capped: True when max_position or available balance reduced the size.
    """

    value: float
    risk_based_value: float
    was_capped: bool


def calculate_position_size(
    portfolio: Portfolio,
    entry_price: float,
    stop_loss_price: float | None,
    risk_params: RiskParams,
) -> PositionSizeResult:
    """Calculate the position size in quote currency.

    Uses the risk-per-trade method: risk a fixed percentage of the portfolio
    on each trade, with the stop-loss distance determining how much to buy.

    Args:
        portfolio: Current portfolio state.
        entry_price: Planned entry price.
        stop_loss_price: Planned stop-loss price. If None, uses the default
            stop-loss percentage from risk_params.
        risk_params: Risk configuration.

    Returns:
        PositionSizeResult with the final size, uncapped risk-based size,
        and whether the size was capped.
    """
    available = portfolio.balance_quote
    if available <= 0:
        return PositionSizeResult(value=0.0, risk_based_value=0.0, was_capped=False)

    risk_amount = available * (risk_params.risk_per_trade_pct / 100)

    max_position = available * (risk_params.max_position_size_pct / 100)

    if stop_loss_price is None:
        stop_loss_distance_pct = risk_params.default_stop_loss_pct / 100
    else:
        stop_loss_distance_pct = abs(entry_price - stop_loss_price) / entry_price

    if stop_loss_distance_pct <= 0:
        stop_loss_distance_pct = risk_params.default_stop_loss_pct / 100

    position_from_risk = risk_amount / stop_loss_distance_pct

    position_size = min(position_from_risk, max_position, available)
    was_capped = position_size < position_from_risk

    logger.debug(
        "Position size: risk_amount=%.2f, stop_distance=%.4f, "
        "position_from_risk=%.2f, max=%.2f, final=%.2f, capped=%s",
        risk_amount,
        stop_loss_distance_pct,
        position_from_risk,
        max_position,
        position_size,
        was_capped,
    )

    return PositionSizeResult(
        value=position_size,
        risk_based_value=position_from_risk,
        was_capped=was_capped,
    )
