"""Stop-loss calculation methods.

Provides different stop-loss strategies that can be selected via configuration.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def fixed_percentage_stop(entry_price: float, stop_pct: float, side: str = "long") -> float:
    """Calculate stop-loss at a fixed percentage from entry.

    Args:
        entry_price: Entry price of the position.
        stop_pct: Stop-loss distance as a percentage (e.g. 3.0 for 3%).
        side: "long" or "short".

    Returns:
        The stop-loss price level.
    """
    distance = entry_price * (stop_pct / 100)
    if side == "long":
        return entry_price - distance
    return entry_price + distance


def atr_based_stop(
    entry_price: float, atr_value: float, multiplier: float = 2.0, side: str = "long"
) -> float:
    """Calculate stop-loss based on Average True Range.

    Places the stop at ``multiplier * ATR`` from the entry price, adapting
    to current market volatility.

    Args:
        entry_price: Entry price of the position.
        atr_value: Current ATR indicator value.
        multiplier: Number of ATRs to use as distance.
        side: "long" or "short".

    Returns:
        The stop-loss price level.
    """
    distance = atr_value * multiplier
    if side == "long":
        return entry_price - distance
    return entry_price + distance
