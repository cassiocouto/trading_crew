"""Position sizing algorithms.

Determines how much capital to allocate to a single trade based on risk
parameters and portfolio state.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from trading_crew.models.portfolio import Portfolio
    from trading_crew.models.risk import RiskParams

logger = logging.getLogger(__name__)


def calculate_position_size(
    portfolio: Portfolio,
    entry_price: float,
    stop_loss_price: float | None,
    risk_params: RiskParams,
) -> float:
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
        Position size in quote currency (e.g. USDT amount to spend).
    """
    available = portfolio.balance_quote
    if available <= 0:
        return 0.0

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

    logger.debug(
        "Position size: risk_amount=%.2f, stop_distance=%.4f, "
        "position_from_risk=%.2f, max=%.2f, final=%.2f",
        risk_amount,
        stop_loss_distance_pct,
        position_from_risk,
        max_position,
        position_size,
    )

    return position_size
