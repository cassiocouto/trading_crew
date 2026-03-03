"""Pydantic data models for the trading domain.

This package contains all the value objects and data transfer objects used
throughout the system. All models are immutable (frozen) by default to
prevent accidental mutation.

Modules:
    market   — Market data: Ticker, OHLCV, OrderBookEntry, MarketAnalysis
    signal   — Trade signals: TradeSignal, SignalStrength, SignalType
    order    — Orders: OrderRequest, Order, OrderStatus, OrderSide, OrderType
    portfolio — Portfolio state: Position, Portfolio, PnLSnapshot
    risk     — Risk parameters: RiskParams, RiskCheckResult, RiskVerdict
"""

from trading_crew.models.cycle import CycleState
from trading_crew.models.market import (
    OHLCV,
    MarketAnalysis,
    OrderBookEntry,
    Ticker,
)
from trading_crew.models.order import (
    Order,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
)
from trading_crew.models.portfolio import (
    PnLSnapshot,
    Portfolio,
    Position,
)
from trading_crew.models.risk import (
    RiskCheckResult,
    RiskParams,
    RiskVerdict,
)
from trading_crew.models.signal import (
    SignalStrength,
    SignalType,
    TradeSignal,
)

__all__ = [
    "OHLCV",
    "CycleState",
    "MarketAnalysis",
    "Order",
    "OrderBookEntry",
    "OrderRequest",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "PnLSnapshot",
    "Portfolio",
    "Position",
    "RiskCheckResult",
    "RiskParams",
    "RiskVerdict",
    "SignalStrength",
    "SignalType",
    "Ticker",
    "TradeSignal",
]
