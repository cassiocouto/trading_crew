"""CCXT-based multi-exchange service.

Provides a unified, exchange-agnostic interface for fetching market data and
placing orders. This replaces the NovaDAX-specific client from silvia_v2 and
supports 100+ exchanges through CCXT's unified API.

Key features:
  - Automatic exchange instantiation from config
  - Paper-trading mode (no real orders placed)
  - Retry logic with exponential backoff
  - Rate-limit awareness
  - Precision handling per exchange/symbol

Usage:
    from trading_crew.services.exchange_service import ExchangeService

    service = ExchangeService()
    ticker = service.fetch_ticker("BTC/USDT")
    candles = service.fetch_ohlcv("BTC/USDT", timeframe="1h", limit=100)
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, TypeVar

import ccxt

from trading_crew.models.market import OHLCV, Ticker
from trading_crew.models.order import (
    Order,
    OrderFill,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_T = TypeVar("_T")

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_RETRY_DELAY = 1.0


class ExchangeService:
    """Unified exchange interface built on CCXT.

    Supports any exchange that CCXT supports. In paper-trading mode,
    order placement is simulated without calling the exchange API.

    Args:
        exchange_id: CCXT exchange identifier (e.g. "binance", "novadax").
        api_key: Exchange API key.
        api_secret: Exchange API secret.
        password: Exchange password (some exchanges require this).
        sandbox: Whether to use the exchange's testnet/sandbox.
        paper_mode: If True, simulate orders locally without exchange calls.
    """

    def __init__(
        self,
        exchange_id: str = "binance",
        api_key: str = "",
        api_secret: str = "",
        password: str = "",
        sandbox: bool = True,
        paper_mode: bool = True,
    ) -> None:
        self._exchange_id = exchange_id
        self._paper_mode = paper_mode

        exchange_class = getattr(ccxt, exchange_id, None)
        if exchange_class is None:
            raise ValueError(
                f"Unknown exchange: {exchange_id}. Available: {', '.join(ccxt.exchanges[:10])}..."
            )

        config: dict[str, object] = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
        }
        if password:
            config["password"] = password

        self._exchange: ccxt.Exchange = exchange_class(config)

        if sandbox:
            try:
                self._exchange.set_sandbox_mode(True)
                logger.info("Exchange %s sandbox mode enabled", exchange_id)
            except ccxt.NotSupported:
                logger.warning(
                    "Exchange %s does not support sandbox mode — "
                    "using production API (paper_mode=%s)",
                    exchange_id,
                    paper_mode,
                )

        logger.info(
            "ExchangeService initialized: exchange=%s, paper=%s, sandbox=%s",
            exchange_id,
            paper_mode,
            sandbox,
        )

    @classmethod
    def from_settings(cls) -> ExchangeService:
        """Create an ExchangeService from the application settings."""
        from trading_crew.config.settings import get_settings

        s = get_settings()
        return cls(
            exchange_id=s.exchange_id,
            api_key=s.exchange_api_key,
            api_secret=s.exchange_api_secret,
            password=s.exchange_password,
            sandbox=s.exchange_sandbox,
            paper_mode=s.is_paper,
        )

    @property
    def exchange_id(self) -> str:
        """The CCXT exchange identifier."""
        return self._exchange_id

    @property
    def is_paper(self) -> bool:
        """Whether this service is in paper-trading mode."""
        return self._paper_mode

    # -- Market Data ----------------------------------------------------------

    def fetch_ticker(self, symbol: str) -> Ticker:
        """Fetch the current ticker for a trading pair.

        Args:
            symbol: Trading pair in CCXT format (e.g. "BTC/USDT").

        Returns:
            A Ticker domain model with bid, ask, last, and volume.

        Raises:
            ccxt.BaseError: On exchange API failures after retries.
        """
        raw = self._retry(lambda: self._exchange.fetch_ticker(symbol))
        return Ticker(
            symbol=symbol,
            exchange=self._exchange_id,
            bid=float(raw.get("bid") or 0),
            ask=float(raw.get("ask") or 0),
            last=float(raw.get("last") or 0),
            volume_24h=float(raw.get("baseVolume") or 0),
            timestamp=datetime.fromtimestamp((raw.get("timestamp") or 0) / 1000, tz=UTC),
        )

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> list[OHLCV]:
        """Fetch OHLCV candles for a trading pair.

        Args:
            symbol: Trading pair.
            timeframe: Candle period (e.g. "1m", "5m", "1h", "1d").
            limit: Maximum number of candles to fetch.

        Returns:
            A list of OHLCV domain models, oldest first.
        """
        raw_candles = self._retry(
            lambda: self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        )
        return [
            OHLCV(
                symbol=symbol,
                exchange=self._exchange_id,
                timeframe=timeframe,
                timestamp=datetime.fromtimestamp(candle[0] / 1000, tz=UTC),
                open=float(candle[1]),
                high=float(candle[2]),
                low=float(candle[3]),
                close=float(candle[4]),
                volume=float(candle[5]),
            )
            for candle in raw_candles
        ]

    def fetch_order_book(self, symbol: str, limit: int = 20) -> dict[str, list[list[float]]]:
        """Fetch the order book for a trading pair.

        Args:
            symbol: Trading pair.
            limit: Depth of the order book per side.

        Returns:
            Dictionary with "bids" and "asks" as lists of [price, amount].
        """
        raw = self._retry(lambda: self._exchange.fetch_order_book(symbol, limit))
        return {"bids": raw.get("bids", []), "asks": raw.get("asks", [])}

    def fetch_balance(self) -> dict[str, float]:
        """Fetch available balances on the exchange.

        Returns:
            Dictionary mapping currency codes to free (available) balances.
            Only includes currencies with non-zero balances.
        """
        if self._paper_mode:
            logger.debug("Paper mode: returning empty balance")
            return {}

        raw = self._retry(lambda: self._exchange.fetch_balance())
        free: dict[str, float] = raw.get("free", {})
        return {k: float(v) for k, v in free.items() if v and float(v) > 0}

    # -- Order Management -----------------------------------------------------

    def create_order(self, request: OrderRequest) -> Order:
        """Place an order on the exchange (or simulate in paper mode).

        Args:
            request: A validated, risk-approved order request.

        Returns:
            An Order domain model with the exchange-assigned ID and status.
        """
        if self._paper_mode:
            return self._simulate_order(request)

        order_params: dict[str, object] = {}

        raw = self._retry(
            lambda: self._exchange.create_order(
                symbol=request.symbol,
                type=request.order_type.value,
                side=request.side.value,
                amount=request.amount,
                price=request.price if request.order_type == OrderType.LIMIT else None,
                params=order_params,
            )
        )

        status_map = {
            "open": OrderStatus.OPEN,
            "closed": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELLED,
            "cancelled": OrderStatus.CANCELLED,
            "expired": OrderStatus.CANCELLED,
            "rejected": OrderStatus.REJECTED,
        }

        return Order(
            id=str(raw["id"]),
            request=request,
            status=status_map.get(raw.get("status", "open"), OrderStatus.OPEN),
            filled_amount=float(raw.get("filled") or 0),
            average_fill_price=float(raw["average"]) if raw.get("average") else None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            exchange_data=raw,
        )

    def fetch_order_status(self, order_id: str, symbol: str) -> dict[str, object]:
        """Fetch the current status of an order from the exchange.

        Args:
            order_id: Exchange-assigned order ID.
            symbol: Trading pair.

        Returns:
            Raw exchange response dictionary.
        """
        if self._paper_mode:
            return {"id": order_id, "status": "closed", "filled": 0, "remaining": 0}

        return self._retry(lambda: self._exchange.fetch_order(order_id, symbol))

    def cancel_order(self, order_id: str, symbol: str) -> None:
        """Cancel an open order on the exchange.

        Args:
            order_id: Exchange-assigned order ID.
            symbol: Trading pair.
        """
        if self._paper_mode:
            logger.info("[PAPER] Cancelled order %s", order_id)
            return

        self._retry(lambda: self._exchange.cancel_order(order_id, symbol))
        logger.info("Cancelled order %s on %s", order_id, symbol)

    # -- Paper Trading --------------------------------------------------------

    #: Default slippage applied to paper market orders (basis points).
    #: 10 bps = 0.1%. Buy orders slip up, sell orders slip down.
    DEFAULT_SLIPPAGE_BPS: float = 10.0

    #: Default taker fee for paper fills (0.1%).
    DEFAULT_PAPER_FEE_RATE: float = 0.001

    def _simulate_order(self, request: OrderRequest) -> Order:
        """Simulate an order fill for paper-trading mode.

        For limit orders, fills at the requested price. For market orders,
        fetches the current ticker to get a realistic execution price and
        applies a slippage model to avoid optimistic fills.

        Raises:
            ValueError: If the fill price cannot be determined (market order
                with no ticker data and no explicit price).
        """
        simulated_id = f"paper-{uuid.uuid4().hex[:12]}"

        if request.order_type == OrderType.LIMIT:
            if request.price is None:
                raise ValueError("Limit order requires a price")
            fill_price = request.price
        else:
            fill_price = self._get_market_fill_price(request.symbol, request.side)

        simulated_fee = fill_price * request.amount * self.DEFAULT_PAPER_FEE_RATE
        fee_currency = request.symbol.split("/")[1] if "/" in request.symbol else "USDT"

        fill = OrderFill(
            price=fill_price,
            amount=request.amount,
            fee=simulated_fee,
            fee_currency=fee_currency,
            timestamp=datetime.now(UTC),
        )

        order = Order(
            id=simulated_id,
            request=request,
            status=OrderStatus.FILLED,
            filled_amount=request.amount,
            average_fill_price=fill_price,
            fills=[fill],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            exchange_data={"simulated": True, "slippage_bps": self.DEFAULT_SLIPPAGE_BPS},
        )

        logger.info(
            "[PAPER] %s %s %.6f %s @ %.2f (fee: %.4f %s)",
            request.side.value.upper(),
            request.order_type.value,
            request.amount,
            request.symbol,
            fill_price,
            simulated_fee,
            fee_currency,
        )
        return order

    def _get_market_fill_price(self, symbol: str, side: OrderSide) -> float:
        """Determine a realistic fill price for a paper market order.

        Fetches the live ticker and applies slippage: buys fill at the ask
        plus slippage, sells fill at the bid minus slippage.

        Raises:
            ValueError: If the ticker returns no usable price data (all zeros).
        """
        ticker = self.fetch_ticker(symbol)
        slippage_mult = self.DEFAULT_SLIPPAGE_BPS / 10_000

        if side == OrderSide.BUY:
            base_price = ticker.ask if ticker.ask > 0 else ticker.last
        else:
            base_price = ticker.bid if ticker.bid > 0 else ticker.last

        if base_price <= 0:
            raise ValueError(
                f"Cannot determine fill price for {symbol}: ticker returned "
                f"bid={ticker.bid}, ask={ticker.ask}, last={ticker.last}. "
                f"The exchange may be unreachable or the pair may be invalid."
            )

        if side == OrderSide.BUY:
            return base_price * (1 + slippage_mult)
        return base_price * (1 - slippage_mult)

    # -- Precision & Market Limits --------------------------------------------

    def _ensure_markets_loaded(self) -> None:
        """Lazy-load CCXT market metadata if not already available.

        Called before any precision or limit lookup. In paper mode we still
        attempt to load markets so precision rounding works correctly; if the
        exchange is unreachable we silently skip and fall back to raw values.
        """
        if self._exchange.markets:
            return
        try:
            self._exchange.load_markets()
            logger.debug("Markets loaded for %s (%d symbols)", self._exchange_id, len(self._exchange.markets))
        except Exception as exc:
            logger.warning("Could not load markets for %s: %s (precision rounding will be skipped)", self._exchange_id, exc)

    def normalize_order_precision(
        self, symbol: str, amount: float, price: float | None = None
    ) -> tuple[float, float | None]:
        """Round amount and price to the exchange's required precision.

        Uses CCXT's ``amount_to_precision`` / ``price_to_precision`` helpers
        which apply the exchange-specific lot-size and tick-size rules.

        Args:
            symbol: Trading pair (e.g. ``"BTC/USDT"``).
            amount: Raw order amount before rounding.
            price: Raw limit price before rounding (``None`` for market orders).

        Returns:
            ``(rounded_amount, rounded_price)`` where ``rounded_price`` is
            ``None`` for market orders.
        """
        self._ensure_markets_loaded()

        if not self._exchange.markets or symbol not in self._exchange.markets:
            logger.debug("No market data for %s — returning raw values", symbol)
            return amount, price

        try:
            rounded_amount = float(self._exchange.amount_to_precision(symbol, amount))
        except Exception as exc:
            logger.warning("amount_to_precision failed for %s: %s — using raw amount", symbol, exc)
            rounded_amount = amount

        rounded_price: float | None = None
        if price is not None:
            try:
                rounded_price = float(self._exchange.price_to_precision(symbol, price))
            except Exception as exc:
                logger.warning("price_to_precision failed for %s: %s — using raw price", symbol, exc)
                rounded_price = price

        return rounded_amount, rounded_price

    def get_market_limits(self, symbol: str) -> dict[str, float | None]:
        """Return the minimum order constraints for a symbol.

        Returns:
            Dictionary with keys ``amount_min``, ``cost_min``, ``price_min``.
            Values are ``None`` when the exchange does not publish the limit.
        """
        self._ensure_markets_loaded()

        empty: dict[str, float | None] = {"amount_min": None, "cost_min": None, "price_min": None}

        if not self._exchange.markets or symbol not in self._exchange.markets:
            return empty

        market = self._exchange.markets[symbol]
        limits = market.get("limits") or {}
        amount_limits = limits.get("amount") or {}
        cost_limits = limits.get("cost") or {}
        price_limits = limits.get("price") or {}

        return {
            "amount_min": float(amount_limits["min"]) if amount_limits.get("min") is not None else None,
            "cost_min": float(cost_limits["min"]) if cost_limits.get("min") is not None else None,
            "price_min": float(price_limits["min"]) if price_limits.get("min") is not None else None,
        }

    # -- Retry Logic ----------------------------------------------------------

    @staticmethod
    def _retry(fn: Callable[[], _T], max_retries: int = MAX_RETRIES) -> _T:
        """Execute a function with exponential backoff retry.

        Handles transient exchange errors (rate limits, network issues)
        gracefully. Permanent errors are re-raised immediately.
        """
        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                return fn()
            except (ccxt.RateLimitExceeded, ccxt.NetworkError, ccxt.RequestTimeout) as e:
                last_error = e
                delay = BASE_RETRY_DELAY * (2**attempt)
                logger.warning(
                    "Exchange error (attempt %d/%d): %s. Retrying in %.1fs",
                    attempt + 1,
                    max_retries,
                    str(e)[:100],
                    delay,
                )
                time.sleep(delay)
            except ccxt.BaseError:
                raise

        raise last_error  # type: ignore[misc]
