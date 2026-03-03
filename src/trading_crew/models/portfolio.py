"""Portfolio and position models.

These models track the current state of holdings, open positions, and
profit-and-loss across the entire portfolio.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Position(BaseModel):
    """An open position in a single trading pair.

    Attributes:
        symbol: Trading pair (e.g. "BTC/USDT").
        exchange: Exchange where the position is held.
        side: "long" or "short" (short selling is exchange-dependent).
        entry_price: Average entry price across all fills.
        amount: Current position size in base currency.
        current_price: Most recent market price for P&L calculation.
        stop_loss_price: Active stop-loss level.
        take_profit_price: Active take-profit level.
        opened_at: When the position was first opened.
        strategy_name: Which strategy opened this position.
        order_ids: IDs of orders that built this position.
    """

    symbol: str
    exchange: str
    side: str = "long"
    entry_price: float = Field(gt=0)
    amount: float = Field(gt=0)
    current_price: float = Field(gt=0)
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    opened_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    strategy_name: str = ""
    order_ids: list[str] = Field(default_factory=list)

    @property
    def unrealized_pnl(self) -> float:
        """Unrealized profit/loss in quote currency."""
        if self.side == "long":
            return (self.current_price - self.entry_price) * self.amount
        return (self.entry_price - self.current_price) * self.amount

    @property
    def unrealized_pnl_pct(self) -> float:
        """Unrealized P&L as a percentage of entry cost."""
        entry_cost = self.entry_price * self.amount
        if entry_cost == 0:
            return 0.0
        return (self.unrealized_pnl / entry_cost) * 100

    @property
    def market_value(self) -> float:
        """Current market value of this position."""
        return self.current_price * self.amount

    @property
    def should_stop_loss(self) -> bool:
        """Whether the stop-loss level has been breached."""
        if self.stop_loss_price is None:
            return False
        if self.side == "long":
            return self.current_price <= self.stop_loss_price
        return self.current_price >= self.stop_loss_price


class PnLSnapshot(BaseModel, frozen=True):
    """Point-in-time profit and loss record.

    Attributes:
        timestamp: When this snapshot was taken.
        total_balance_quote: Total portfolio value in quote currency.
        unrealized_pnl: Sum of unrealized P&L across all positions.
        realized_pnl: Cumulative realized P&L from closed positions.
        total_fees: Cumulative fees paid.
        num_open_positions: Count of open positions.
        drawdown_pct: Current drawdown from peak balance as a percentage.
    """

    timestamp: datetime
    total_balance_quote: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    total_fees: float = 0.0
    num_open_positions: int = 0
    drawdown_pct: float = 0.0


class Portfolio(BaseModel):
    """Aggregate portfolio state.

    Attributes:
        positions: Currently open positions, keyed by symbol.
        balance_quote: Available quote currency balance (e.g. USDT, BRL).
        quote_currency: The quote currency used for valuation.
        realized_pnl: Cumulative realized P&L from closed trades.
        total_fees: Cumulative fees paid across all trades.
        peak_balance: Highest total balance seen (for drawdown calculation).
        pnl_history: Historical P&L snapshots for equity curve.
    """

    positions: dict[str, Position] = Field(default_factory=dict)
    balance_quote: float = Field(default=0.0, ge=0)
    quote_currency: str = "USDT"
    realized_pnl: float = 0.0
    total_fees: float = 0.0
    peak_balance: float = 0.0
    pnl_history: list[PnLSnapshot] = Field(default_factory=list)

    @property
    def total_market_value(self) -> float:
        """Total value of all open positions."""
        return sum(p.market_value for p in self.positions.values())

    @property
    def total_balance(self) -> float:
        """Total portfolio value (positions + available balance)."""
        return self.total_market_value + self.balance_quote

    @property
    def total_unrealized_pnl(self) -> float:
        """Sum of unrealized P&L across all positions."""
        return sum(p.unrealized_pnl for p in self.positions.values())

    @property
    def drawdown_pct(self) -> float:
        """Current drawdown from peak balance as a percentage."""
        if self.peak_balance == 0:
            return 0.0
        return ((self.peak_balance - self.total_balance) / self.peak_balance) * 100

    @property
    def exposure_pct(self) -> float:
        """Percentage of portfolio currently in positions."""
        if self.total_balance == 0:
            return 0.0
        return (self.total_market_value / self.total_balance) * 100

    def update_peak(self) -> None:
        """Update peak balance if current total exceeds it."""
        if self.total_balance > self.peak_balance:
            self.peak_balance = self.total_balance

    def snapshot(self) -> PnLSnapshot:
        """Create a point-in-time P&L snapshot."""
        return PnLSnapshot(
            timestamp=datetime.now(timezone.utc),
            total_balance_quote=self.total_balance,
            unrealized_pnl=self.total_unrealized_pnl,
            realized_pnl=self.realized_pnl,
            total_fees=self.total_fees,
            num_open_positions=len(self.positions),
            drawdown_pct=self.drawdown_pct,
        )
