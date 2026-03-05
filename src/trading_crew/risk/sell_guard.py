"""Pluggable sell-guard interface and implementations.

A ``SellGuard`` is injected into ``RiskPipeline`` and called for every SELL
signal *after* the inventory check.  It receives the pre-fetched break-even
price for the symbol (computed once at fill time and stored in the DB) so the
pipeline stays I/O-free.

To add a custom guard:
  1. Subclass ``SellGuard`` and implement ``evaluate()``.
  2. Instantiate it in ``main.py`` and pass it to ``RiskPipeline``.

The guard is *not* called for stop-loss exits — those happen in
``ExecutionService._poll_single_order`` and bypass the signal pipeline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from trading_crew.models.risk import RiskParams


class SellGuard(ABC):
    """Abstract base for sell-signal validation."""

    @abstractmethod
    def evaluate(
        self,
        symbol: str,
        proposed_price: float,
        break_even_price: float | None,
        risk_params: RiskParams,
    ) -> tuple[bool, str]:
        """Decide whether to allow a sell at ``proposed_price``.

        Args:
            symbol: Trading pair being sold.
            proposed_price: Signal's entry price (the intended sell price).
            break_even_price: Persisted break-even from the most recently
                filled BUY order for this symbol, or ``None`` if no prior buy
                is on record.
            risk_params: Current risk configuration (provides
                ``min_profit_margin_pct``).

        Returns:
            ``(allow, reason)`` — if ``allow`` is False the signal is rejected
            and ``reason`` is logged and recorded in ``RiskCheckResult.reasons``.
        """


class AllowAllSellGuard(SellGuard):
    """Pass-through guard — every sell is allowed.

    Used as the default in backtest mode and when ``SELL_GUARD_MODE=none``.
    """

    def evaluate(
        self,
        symbol: str,
        proposed_price: float,
        break_even_price: float | None,
        risk_params: RiskParams,
    ) -> tuple[bool, str]:
        return True, "no guard"


class BreakEvenSellGuard(SellGuard):
    """LIFO break-even guard — holds positions until the most recent lot is profitable.

    Uses the ``break_even_price`` stored on the most recently filled BUY order
    (LIFO lot matching) plus ``risk_params.min_profit_margin_pct`` to compute
    the minimum acceptable sell price:

        min_sell = break_even_price * (1 + min_profit_margin_pct / 100)

    If the proposed price is below ``min_sell``, the signal is rejected and the
    position is held.  Stop-loss exits are *not* affected — they bypass the
    guard entirely.
    """

    def evaluate(
        self,
        symbol: str,
        proposed_price: float,
        break_even_price: float | None,
        risk_params: RiskParams,
    ) -> tuple[bool, str]:
        if break_even_price is None:
            return True, "no break-even on record — allowing sell"

        margin = risk_params.min_profit_margin_pct
        min_sell = break_even_price * (1.0 + margin / 100.0)

        if proposed_price < min_sell:
            return False, (
                f"holding — min sell {min_sell:.4f} "
                f"(break-even {break_even_price:.4f}"
                + (f" + {margin}% margin" if margin > 0 else "")
                + f"), proposed {proposed_price:.4f}"
            )
        return True, f"price {proposed_price:.4f} clears min sell {min_sell:.4f}"
