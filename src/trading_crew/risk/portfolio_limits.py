"""Portfolio-level risk limits.

Checks that a proposed trade doesn't violate portfolio-wide constraints
such as maximum exposure and single-asset concentration limits.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from trading_crew.models.portfolio import Portfolio
    from trading_crew.models.risk import RiskParams

logger = logging.getLogger(__name__)


def check_exposure_limit(
    portfolio: Portfolio,
    proposed_position_value: float,
    risk_params: RiskParams,
) -> tuple[bool, str]:
    """Check if adding a position would exceed the portfolio exposure limit.

    Args:
        portfolio: Current portfolio state.
        proposed_position_value: Value of the proposed new position.
        risk_params: Risk configuration.

    Returns:
        Tuple of (passes, reason). If passes is False, the reason explains why.
    """
    current_exposure = portfolio.total_market_value
    total_balance = portfolio.total_balance

    if total_balance <= 0:
        return False, "Portfolio balance is zero"

    new_exposure_pct = ((current_exposure + proposed_position_value) / total_balance) * 100

    if new_exposure_pct > risk_params.max_portfolio_exposure_pct:
        return False, (
            f"Would exceed portfolio exposure limit: {new_exposure_pct:.1f}% "
            f"> {risk_params.max_portfolio_exposure_pct:.1f}%"
        )

    return True, "Exposure within limits"


def check_concentration_limit(
    portfolio: Portfolio,
    symbol: str,
    proposed_position_value: float,
    risk_params: RiskParams,
) -> tuple[bool, str]:
    """Check if a position in a single asset would exceed concentration limits.

    Args:
        portfolio: Current portfolio state.
        symbol: The trading pair.
        proposed_position_value: Value of the proposed position.
        risk_params: Risk configuration.

    Returns:
        Tuple of (passes, reason).
    """
    total_balance = portfolio.total_balance
    if total_balance <= 0:
        return False, "Portfolio balance is zero"

    existing_value = 0.0
    if symbol in portfolio.positions:
        existing_value = portfolio.positions[symbol].market_value

    total_in_symbol_pct = ((existing_value + proposed_position_value) / total_balance) * 100

    if total_in_symbol_pct > risk_params.max_position_size_pct:
        return False, (
            f"Would exceed single-asset limit for {symbol}: {total_in_symbol_pct:.1f}% "
            f"> {risk_params.max_position_size_pct:.1f}%"
        )

    return True, "Concentration within limits"
