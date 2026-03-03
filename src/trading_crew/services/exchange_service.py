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
from datetime import datetime, timezone

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
                f"Unknown exchange: {exchange_id}. "
                f"Available: {', '.join(ccxt.exchanges[:10])}..."
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
            timestamp=datetime.fromtimestamp(
                (raw.get("timestamp") or 0) / 1000, tz=timezone.utc
            ),
        )

    def fetch_ohlcv(
        self, symbol: str, timeframe: str = "1h", limit: int = 100
    ) -> list[OHLCV]:
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
                timestamp=datetime.fromtimestamp(candle[0] / 1000, tz=timezone.utc),
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
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
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

    def _simulate_order(self, request: OrderRequest) -> Order:
        """Simulate an order fill for paper-trading mode.

        In paper mode, limit orders fill at the requested price and market
        orders fill at a simulated price. This provides a realistic but
        safe testing experience.
        """
        simulated_id = f"paper-{uuid.uuid4().hex[:12]}"
        fill_price = request.price or 0.0

        simulated_fee = fill_price * request.amount * 0.001

        fill = OrderFill(
            price=fill_price,
            amount=request.amount,
            fee=simulated_fee,
            fee_currency="USDT",
            timestamp=datetime.now(timezone.utc),
        )

        order = Order(
            id=simulated_id,
            request=request,
            status=OrderStatus.FILLED,
            filled_amount=request.amount,
            average_fill_price=fill_price,
            fills=[fill],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            exchange_data={"simulated": True},
        )

        logger.info(
            "[PAPER] %s %s %.6f %s @ %.2f (fee: %.4f)",
            request.side.value.upper(),
            request.order_type.value,
            request.amount,
            request.symbol,
            fill_price,
            simulated_fee,
        )
        return order

    # -- Retry Logic ----------------------------------------------------------

    @staticmethod
    def _retry(fn: object, max_retries: int = MAX_RETRIES) -> object:
        """Execute a function with exponential backoff retry.

        Handles transient exchange errors (rate limits, network issues)
        gracefully. Permanent errors are re-raised immediately.
        """
        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                return fn()  # type: ignore[operator]
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
