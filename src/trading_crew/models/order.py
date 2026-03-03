"""Order models.

These models represent the full lifecycle of a trade order — from the initial
request through placement, partial fills, and final completion or cancellation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class OrderSide(str, Enum):
    """Direction of an order."""

    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Execution type of an order."""

    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    """Lifecycle state of an order.

    State transitions:
        PENDING → OPEN → FILLED
        PENDING → OPEN → PARTIALLY_FILLED → FILLED
        PENDING → OPEN → CANCELLED
        PENDING → REJECTED
    """

    PENDING = "pending"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

    @property
    def is_terminal(self) -> bool:
        """Whether this status represents a final state."""
        return self in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED)

    @property
    def is_active(self) -> bool:
        """Whether this order is still live on the exchange."""
        return self in (OrderStatus.PENDING, OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)


class OrderRequest(BaseModel, frozen=True):
    """A validated, risk-approved request to place an order.

    Created by the Risk Manager Agent after validating a TradeSignal.
    Consumed by the Executor Agent.

    Attributes:
        symbol: Trading pair.
        exchange: Target exchange.
        side: Buy or sell.
        order_type: Market or limit.
        amount: Quantity in base currency.
        price: Limit price (required for limit orders, ignored for market).
        stop_loss_price: Stop-loss level set by the Risk Manager.
        take_profit_price: Take-profit level.
        strategy_name: Originating strategy for traceability.
        signal_confidence: Confidence score from the original signal.
    """

    symbol: str
    exchange: str
    side: OrderSide
    order_type: OrderType
    amount: float = Field(gt=0)
    price: float | None = None
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    strategy_name: str = ""
    signal_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class OrderFill(BaseModel, frozen=True):
    """A single fill (partial or complete) on an order.

    Attributes:
        price: Execution price.
        amount: Filled quantity.
        fee: Fee charged by the exchange.
        fee_currency: Currency of the fee (e.g. "USDT", "BNB").
        timestamp: When this fill occurred.
    """

    price: float = Field(gt=0)
    amount: float = Field(gt=0)
    fee: float = Field(ge=0, default=0.0)
    fee_currency: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Order(BaseModel):
    """A placed order with its current state.

    This model is mutable (not frozen) because order status and fills
    are updated as the exchange reports changes.

    Attributes:
        id: Exchange-assigned order ID.
        request: The original order request.
        status: Current lifecycle state.
        filled_amount: Total quantity filled so far.
        average_fill_price: Volume-weighted average fill price.
        fills: Individual fill records.
        created_at: When the order was placed.
        updated_at: Last status update time.
        exchange_data: Raw exchange response for debugging.
    """

    id: str
    request: OrderRequest
    status: OrderStatus = OrderStatus.PENDING
    filled_amount: float = Field(default=0.0, ge=0)
    average_fill_price: float | None = None
    fills: list[OrderFill] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    exchange_data: dict[str, object] = Field(default_factory=dict)

    @property
    def remaining_amount(self) -> float:
        """Quantity still unfilled."""
        return self.request.amount - self.filled_amount

    @property
    def fill_pct(self) -> float:
        """Percentage of the order that has been filled."""
        if self.request.amount == 0:
            return 0.0
        return (self.filled_amount / self.request.amount) * 100

    @property
    def total_fee(self) -> float:
        """Sum of all fees across fills."""
        return sum(f.fee for f in self.fills)

    def add_fill(self, fill: OrderFill) -> None:
        """Record a new fill and update aggregates."""
        self.fills.append(fill)
        self.filled_amount += fill.amount
        total_cost = sum(f.price * f.amount for f in self.fills)
        total_amount = sum(f.amount for f in self.fills)
        self.average_fill_price = total_cost / total_amount if total_amount > 0 else None
        self.updated_at = datetime.now(timezone.utc)

        if self.filled_amount >= self.request.amount:
            self.status = OrderStatus.FILLED
        elif self.filled_amount > 0:
            self.status = OrderStatus.PARTIALLY_FILLED
