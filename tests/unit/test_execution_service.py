"""Unit tests for ExecutionService (Phase 4 deterministic pipeline).

All exchange, database, and notification interactions are replaced with
lightweight stubs — no real API calls are made.

Test coverage:
  1.  Paper-mode immediate fill — process_order_requests() places + fills
  2.  Live-mode placement — order saved as OPEN, no immediate fill
  3.  Live-mode poll → full fill — poll_and_reconcile() detects filled order
  4.  Partial fill accumulation — incremental reconcile on delta
  5.  Stale fully-open order cancellation
  6.  Stale partial fill cancellation — filled portion reconciled, remainder released
  7.  Dead-letter queue — exchange rejects order, added to failed_orders
  8.  Precision normalization — amount/price rounded before placement
  9.  Order validation: insufficient balance (BUY)
  10. Order validation: no position to sell
  11. Order validation: sell amount exceeds position
  12. Order validation: below min amount
  13. Save-before-place consistency — PENDING saved before call; REJECTED on failure
  14. LIMIT order path — price precision rounded
  15. MARKET order path — price skipped in precision
  16. Portfolio reconciliation: BUY fill math
  17. Portfolio reconciliation: SELL fill math
  18. Portfolio reconciliation: incremental partial fill
  19. Portfolio persistence — save_portfolio() called after poll_and_reconcile()
  20. Notification triggers — verify correct notify methods called
  21. Empty order_requests — noop, returns empty result
  22. Exchange routing stub — always returns configured exchange_id
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from trading_crew.models.order import (
    Order,
    OrderFill,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
)
from trading_crew.models.portfolio import Portfolio, Position
from trading_crew.services.execution_service import (
    ExecutionService,
    FailedOrder,
    _normalize_status,
)

# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------

SYMBOL = "BTC/USDT"
EXCHANGE_ID = "binance"


def _make_buy_request(
    amount: float = 0.01,
    price: float = 50_000.0,
    order_type: OrderType = OrderType.LIMIT,
    strategy_name: str = "ema_crossover",
) -> OrderRequest:
    return OrderRequest(
        symbol=SYMBOL,
        exchange=EXCHANGE_ID,
        side=OrderSide.BUY,
        order_type=order_type,
        amount=amount,
        price=price if order_type == OrderType.LIMIT else None,
        strategy_name=strategy_name,
    )


def _make_sell_request(amount: float = 0.01, price: float = 55_000.0) -> OrderRequest:
    return OrderRequest(
        symbol=SYMBOL,
        exchange=EXCHANGE_ID,
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        amount=amount,
        price=price,
        strategy_name="ema_crossover",
    )


def _make_filled_order(request: OrderRequest, fill_price: float | None = None) -> Order:
    fp = fill_price or request.price or 50_000.0
    fee_currency = SYMBOL.split("/")[1]
    fill = OrderFill(
        price=fp,
        amount=request.amount,
        fee=fp * request.amount * 0.001,
        fee_currency=fee_currency,
        timestamp=datetime.now(UTC),
    )
    order = Order(
        id=f"paper-{uuid.uuid4().hex[:12]}",
        request=request,
        status=OrderStatus.FILLED,
        filled_amount=request.amount,
        average_fill_price=fp,
        fills=[fill],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    return order


def _make_open_order(request: OrderRequest) -> Order:
    return Order(
        id=f"live-{uuid.uuid4().hex[:12]}",
        request=request,
        status=OrderStatus.OPEN,
        filled_amount=0.0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _make_portfolio(balance: float = 10_000.0) -> Portfolio:
    return Portfolio(balance_quote=balance, peak_balance=balance)


def _make_portfolio_with_position(
    symbol: str = SYMBOL,
    amount: float = 0.1,
    entry_price: float = 50_000.0,
    balance: float = 5_000.0,
) -> Portfolio:
    p = Portfolio(balance_quote=balance, peak_balance=balance + entry_price * amount)
    p.positions[symbol] = Position(
        symbol=symbol,
        exchange=EXCHANGE_ID,
        entry_price=entry_price,
        amount=amount,
        current_price=entry_price,
    )
    return p


def _apply_tentative_buy(portfolio: Portfolio, req: OrderRequest) -> None:
    """Mimic Phase 3's _apply_single_order_to_portfolio for a BUY.

    Pre-conditions the portfolio with the tentative reservation that
    ExecutionService._reconcile_fill expects to be present when called.
    """
    price = req.price or 0.0
    portfolio.balance_quote -= req.amount * price
    if req.symbol in portfolio.positions:
        pos = portfolio.positions[req.symbol]
        total = pos.amount + req.amount
        new_entry = (pos.entry_price * pos.amount + price * req.amount) / total
        portfolio.positions[req.symbol] = pos.model_copy(
            update={"amount": total, "entry_price": new_entry}
        )
    else:
        portfolio.positions[req.symbol] = Position(
            symbol=req.symbol,
            exchange=req.exchange,
            entry_price=price,
            amount=req.amount,
            current_price=price,
        )


def _apply_tentative_sell(portfolio: Portfolio, req: OrderRequest) -> None:
    """Mimic Phase 3's _apply_single_order_to_portfolio for a SELL.

    Pre-conditions the portfolio with the tentative reservation that
    ExecutionService._reconcile_fill expects to be present when called.
    """
    price = req.price or 0.0
    if req.symbol not in portfolio.positions:
        return
    pos = portfolio.positions[req.symbol]
    sell_amount = min(req.amount, pos.amount)
    portfolio.balance_quote += sell_amount * price
    remaining = pos.amount - sell_amount
    if remaining <= 1e-10:
        del portfolio.positions[req.symbol]
    else:
        portfolio.positions[req.symbol] = pos.model_copy(update={"amount": remaining})


class _ExchangeStub:
    """Minimal exchange stub."""

    exchange_id = EXCHANGE_ID
    is_paper = True

    def __init__(self, paper: bool = True, fill_price: float = 50_500.0):
        self.is_paper = paper
        self._fill_price = fill_price
        self.created_orders: list[OrderRequest] = []
        self.cancelled_orders: list[str] = []
        self._status_responses: dict[str, dict] = {}

    def create_order(self, request: OrderRequest) -> Order:
        self.created_orders.append(request)
        return _make_filled_order(request, self._fill_price) if self.is_paper else _make_open_order(request)

    def fetch_order_status(self, order_id: str, symbol: str) -> dict:
        return self._status_responses.get(order_id, {"status": "open", "filled": 0, "remaining": 0.01, "average": None})

    def cancel_order(self, order_id: str, symbol: str) -> None:
        self.cancelled_orders.append(order_id)

    def normalize_order_precision(self, symbol: str, amount: float, price: float | None) -> tuple[float, float | None]:
        return round(amount, 6), round(price, 2) if price else None

    def get_market_limits(self, symbol: str) -> dict:
        return {"amount_min": 0.0001, "cost_min": 1.0, "price_min": None}

    def fetch_ticker(self, symbol: str) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(ask=self._fill_price, last=self._fill_price, bid=self._fill_price - 10)


class _FailingExchangeStub(_ExchangeStub):
    """Exchange stub that always raises on create_order."""

    def create_order(self, request: OrderRequest) -> Order:
        raise RuntimeError("Exchange connection refused")


class _DBStub:
    """Minimal database stub tracking calls."""

    def __init__(self) -> None:
        self.saved_orders: list[Order] = []
        self.failed_orders: list[tuple] = []
        self.saved_portfolios: list[Portfolio] = []
        self._open_records: list = []

    def save_order(self, order: Order) -> None:
        self.saved_orders.append(order)

    def finalize_pending_order(self, pending_id: str, placed_order: Order) -> bool:
        """Stub: record the finalization call without actually modifying orders."""
        return any(o.id == pending_id for o in self.saved_orders)

    def get_open_orders(self) -> list:
        return self._open_records

    def update_order_status_by_exchange_id(self, exchange_order_id: str, status: str) -> bool:
        for r in self._open_records:
            if r.exchange_order_id == exchange_order_id:
                r.status = status
                return True
        return False

    def save_failed_order(self, order_request: OrderRequest, error_reason: str) -> None:
        self.failed_orders.append((order_request, error_reason))

    def save_portfolio(self, portfolio: Portfolio) -> None:
        self.saved_portfolios.append(portfolio)


class _NotifStub:
    """Minimal notification stub tracking calls."""

    def __init__(self) -> None:
        self.notifications: list[str] = []
        self.errors: list[str] = []

    def notify(self, message: str) -> None:
        self.notifications.append(message)

    def notify_error(self, message: str) -> None:
        self.errors.append(message)


class _FakeOrderRecord:
    """Plain-Python substitute for OrderRecord used in unit tests.

    Avoids SQLAlchemy ORM instrumentation requirements while providing the
    same attribute interface that ExecutionService reads from DB records.
    """

    def __init__(
        self,
        exchange_order_id: str,
        symbol: str = SYMBOL,
        exchange: str = EXCHANGE_ID,
        side: str = "buy",
        order_type: str = "limit",
        status: str = "open",
        requested_amount: float = 0.01,
        filled_amount: float = 0.0,
        requested_price: float = 50_000.0,
        average_fill_price: float | None = None,
        stop_loss_price: float | None = None,
        take_profit_price: float | None = None,
        strategy_name: str = "ema_crossover",
        created_at: datetime | None = None,
    ) -> None:
        self.exchange_order_id = exchange_order_id
        self.symbol = symbol
        self.exchange = exchange
        self.side = side
        self.order_type = order_type
        self.status = status
        self.requested_amount = requested_amount
        self.filled_amount = filled_amount
        self.requested_price = requested_price
        self.average_fill_price = average_fill_price
        self.stop_loss_price = stop_loss_price
        self.take_profit_price = take_profit_price
        self.total_fee = 0.0
        self.strategy_name = strategy_name
        self.signal_confidence = 0.0
        self.created_at = created_at or datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
        self.raw_exchange_response = None


def _make_db_record(
    order_id: str,
    symbol: str = SYMBOL,
    exchange: str = EXCHANGE_ID,
    side: str = "buy",
    order_type: str = "limit",
    status: str = "open",
    requested_amount: float = 0.01,
    filled_amount: float = 0.0,
    requested_price: float = 50_000.0,
    stop_loss_price: float | None = None,
    take_profit_price: float | None = None,
    strategy_name: str = "ema_crossover",
    created_at: datetime | None = None,
) -> _FakeOrderRecord:
    """Build a minimal OrderRecord-like object for testing."""
    return _FakeOrderRecord(
        exchange_order_id=order_id,
        symbol=symbol,
        exchange=exchange,
        side=side,
        order_type=order_type,
        status=status,
        requested_amount=requested_amount,
        filled_amount=filled_amount,
        requested_price=requested_price,
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price,
        strategy_name=strategy_name,
        created_at=created_at,
    )


def _make_service(
    exchange: _ExchangeStub | None = None,
    db: _DBStub | None = None,
    notif: _NotifStub | None = None,
    stale_minutes: int = 10,
    stale_partial_minutes: int = 360,
) -> tuple[ExecutionService, _ExchangeStub, _DBStub, _NotifStub]:
    ex = exchange or _ExchangeStub()
    db_ = db or _DBStub()
    nf = notif or _NotifStub()
    svc = ExecutionService(
        exchange_service=ex,
        db_service=db_,
        notification_service=nf,
        stale_order_cancel_minutes=stale_minutes,
        stale_partial_fill_cancel_minutes=stale_partial_minutes,
    )
    return svc, ex, db_, nf


# ---------------------------------------------------------------------------
# 1. Paper-mode immediate fill
# ---------------------------------------------------------------------------


class TestPaperModeImmediateFill:
    def test_order_placed_and_filled(self) -> None:
        svc, _ex, _db, _nf = _make_service()
        req = _make_buy_request()
        portfolio = _make_portfolio(balance=1000.0)
        # Pre-apply tentative reservation (as Phase 3 would)
        portfolio.balance_quote -= req.amount * req.price

        result = svc.process_order_requests([req], portfolio)

        assert len(result.placed) == 1
        assert len(result.filled) == 1
        assert len(result.failed) == 0
        order = result.filled[0]
        assert order.status == OrderStatus.FILLED

    def test_portfolio_updated_after_fill(self) -> None:
        svc, _ex, _db, _nf = _make_service(exchange=_ExchangeStub(paper=True, fill_price=50_500.0))
        req = _make_buy_request(amount=0.01, price=50_000.0)
        portfolio = _make_portfolio(balance=10_000.0)

        svc.process_order_requests([req], portfolio)

        # Position should exist after fill
        assert SYMBOL in portfolio.positions
        pos = portfolio.positions[SYMBOL]
        assert abs(pos.amount - req.amount) < 1e-9

    def test_order_saved_to_db(self) -> None:
        svc, _ex, db, _nf = _make_service()
        req = _make_buy_request()
        portfolio = _make_portfolio()

        svc.process_order_requests([req], portfolio)

        # At least PENDING + actual order saved
        assert len(db.saved_orders) >= 2

    def test_notification_sent_on_fill(self) -> None:
        svc, _ex, _db, nf = _make_service()
        req = _make_buy_request()
        portfolio = _make_portfolio()

        svc.process_order_requests([req], portfolio)

        placed_msgs = [m for m in nf.notifications if "placed" in m.lower()]
        filled_msgs = [m for m in nf.notifications if "filled" in m.lower()]
        assert placed_msgs, "Expected an order-placed notification"
        assert filled_msgs, "Expected an order-filled notification"


# ---------------------------------------------------------------------------
# 2. Live-mode placement (no immediate fill)
# ---------------------------------------------------------------------------


class TestLiveModePlacement:
    def test_order_open_not_filled(self) -> None:
        ex = _ExchangeStub(paper=False)
        svc, ex, _db, _nf = _make_service(exchange=ex)
        req = _make_buy_request()
        portfolio = _make_portfolio()

        result = svc.process_order_requests([req], portfolio)

        assert len(result.placed) == 1
        assert len(result.filled) == 0
        placed = result.placed[0]
        assert placed.status == OrderStatus.OPEN

    def test_no_portfolio_mutation_on_open(self) -> None:
        """Live placement doesn't immediately reconcile portfolio."""
        ex = _ExchangeStub(paper=False)
        svc, *_ = _make_service(exchange=ex)
        req = _make_buy_request(amount=0.01, price=50_000.0)
        portfolio = _make_portfolio(balance=10_000.0)

        svc.process_order_requests([req], portfolio)

        # No position added yet — fill reconcile happens in poll_and_reconcile
        assert SYMBOL not in portfolio.positions


# ---------------------------------------------------------------------------
# 3. Live-mode poll → full fill
# ---------------------------------------------------------------------------


class TestPollFullFill:
    def test_fill_detected_on_poll(self) -> None:
        ex = _ExchangeStub(paper=False)
        order_id = f"live-{uuid.uuid4().hex[:8]}"
        ex._status_responses[order_id] = {
            "status": "closed",
            "filled": 0.01,
            "remaining": 0.0,
            "average": 50_500.0,
        }
        record = _make_db_record(order_id, filled_amount=0.0)
        db = _DBStub()
        db._open_records = [record]

        svc, _, db, _nf = _make_service(exchange=ex, db=db)
        portfolio = _make_portfolio()

        result = svc.poll_and_reconcile(portfolio)

        assert len(result.filled) == 1
        assert result.filled[0].id == order_id
        assert SYMBOL in portfolio.positions

    def test_portfolio_updated_on_fill(self) -> None:
        ex = _ExchangeStub(paper=False)
        order_id = "ord-fill-123"
        ex._status_responses[order_id] = {
            "status": "closed",
            "filled": 0.02,
            "remaining": 0.0,
            "average": 49_000.0,
        }
        record = _make_db_record(order_id, requested_amount=0.02, filled_amount=0.0, requested_price=49_000.0)
        db = _DBStub()
        db._open_records = [record]
        svc, _, db, _ = _make_service(exchange=ex, db=db)
        portfolio = _make_portfolio()

        svc.poll_and_reconcile(portfolio)

        pos = portfolio.positions[SYMBOL]
        assert abs(pos.amount - 0.02) < 1e-9

    def test_fill_notification_sent(self) -> None:
        ex = _ExchangeStub(paper=False)
        order_id = "ord-fill-notif"
        ex._status_responses[order_id] = {"status": "closed", "filled": 0.01, "remaining": 0.0, "average": 50_000.0}
        db = _DBStub()
        db._open_records = [_make_db_record(order_id)]
        svc, _, _, nf = _make_service(exchange=ex, db=db)

        svc.poll_and_reconcile(_make_portfolio())

        filled_msgs = [m for m in nf.notifications if "filled" in m.lower()]
        assert filled_msgs


# ---------------------------------------------------------------------------
# 4. Partial fill accumulation
# ---------------------------------------------------------------------------


class TestPartialFillAccumulation:
    def test_partial_fill_increments_position(self) -> None:
        """Partial fill with Phase 3 tentative: position stays at tentative amount.

        In DETERMINISTIC mode Phase 3 tentatively books the full order amount
        into the portfolio. When a partial fill arrives, only the balance is
        corrected for the price delta; the position remains at the full tentative
        amount until _reconcile_fill resolves everything on the final fill.
        """
        ex = _ExchangeStub(paper=False)
        order_id = "ord-partial-1"
        ex._status_responses[order_id] = {
            "status": "partial",
            "filled": 0.005,
            "remaining": 0.005,
            "average": 50_000.0,
        }
        record = _make_db_record(order_id, requested_amount=0.01, filled_amount=0.0, requested_price=50_000.0)
        db = _DBStub()
        db._open_records = [record]
        svc, _, _, nf = _make_service(exchange=ex, db=db)
        portfolio = _make_portfolio()

        # Pre-apply Phase 3 tentative BUY reservation
        _apply_tentative_buy(portfolio, _make_buy_request(amount=0.01, price=50_000.0))

        result = svc.poll_and_reconcile(portfolio)

        assert len(result.filled) == 0  # not fully filled yet
        assert SYMBOL in portfolio.positions
        pos = portfolio.positions[SYMBOL]
        # Position stays at full tentative amount during partial fills;
        # _reconcile_fill will correct to actual on the final fill.
        assert abs(pos.amount - 0.01) < 1e-9
        partial_msgs = [m for m in nf.notifications if "partial" in m.lower()]
        assert partial_msgs

    def test_second_poll_full_fill_completes(self) -> None:
        ex = _ExchangeStub(paper=False)
        order_id = "ord-partial-2"
        # Second poll returns fully filled
        ex._status_responses[order_id] = {
            "status": "closed",
            "filled": 0.01,
            "remaining": 0.0,
            "average": 50_000.0,
        }
        record = _make_db_record(order_id, requested_amount=0.01, filled_amount=0.005)
        db = _DBStub()
        db._open_records = [record]
        svc, _, _, _ = _make_service(exchange=ex, db=db)
        portfolio = _make_portfolio_with_position(amount=0.005, entry_price=50_000.0)

        result = svc.poll_and_reconcile(portfolio)

        assert len(result.filled) == 1


# ---------------------------------------------------------------------------
# 5. Stale fully-open order cancellation
# ---------------------------------------------------------------------------


class TestStaleFullyOpenCancellation:
    def test_stale_order_cancelled(self) -> None:
        ex = _ExchangeStub(paper=False)
        order_id = "stale-open-1"
        ex._status_responses[order_id] = {
            "status": "open",
            "filled": 0.0,
            "remaining": 0.01,
            "average": None,
        }
        stale_created_at = datetime.now(UTC) - timedelta(minutes=15)
        record = _make_db_record(order_id, created_at=stale_created_at)
        db = _DBStub()
        db._open_records = [record]
        svc, _, _, _nf = _make_service(exchange=ex, db=db, stale_minutes=10)
        portfolio = _make_portfolio()

        result = svc.poll_and_reconcile(portfolio)

        assert order_id in ex.cancelled_orders
        assert len(result.cancelled) == 1

    def test_stale_cancel_notification_sent(self) -> None:
        ex = _ExchangeStub(paper=False)
        order_id = "stale-open-notif"
        ex._status_responses[order_id] = {"status": "open", "filled": 0.0, "remaining": 0.01, "average": None}
        record = _make_db_record(order_id, created_at=datetime.now(UTC) - timedelta(minutes=20))
        db = _DBStub()
        db._open_records = [record]
        svc, _, _, nf = _make_service(exchange=ex, db=db, stale_minutes=10)

        svc.poll_and_reconcile(_make_portfolio())

        cancel_msgs = [m for m in nf.notifications if "cancel" in m.lower() or "stale" in m.lower()]
        assert cancel_msgs

    def test_fresh_order_not_cancelled(self) -> None:
        ex = _ExchangeStub(paper=False)
        order_id = "fresh-open-1"
        ex._status_responses[order_id] = {"status": "open", "filled": 0.0, "remaining": 0.01, "average": None}
        record = _make_db_record(order_id, created_at=datetime.now(UTC) - timedelta(minutes=2))
        db = _DBStub()
        db._open_records = [record]
        svc, _, _, _ = _make_service(exchange=ex, db=db, stale_minutes=10)

        result = svc.poll_and_reconcile(_make_portfolio())

        assert order_id not in ex.cancelled_orders
        assert len(result.cancelled) == 0


# ---------------------------------------------------------------------------
# 6. Stale partial fill cancellation
# ---------------------------------------------------------------------------


class TestStalePartialFillCancellation:
    def test_stale_partial_fill_cancelled(self) -> None:
        ex = _ExchangeStub(paper=False)
        order_id = "stale-partial-1"
        ex._status_responses[order_id] = {
            "status": "partial",
            "filled": 0.005,
            "remaining": 0.005,
            "average": 50_000.0,
        }
        stale_created = datetime.now(UTC) - timedelta(minutes=400)
        record = _make_db_record(
            order_id,
            status="partially_filled",
            filled_amount=0.004,
            created_at=stale_created,
        )
        db = _DBStub()
        db._open_records = [record]
        svc, _, _, _nf = _make_service(exchange=ex, db=db, stale_partial_minutes=360)
        portfolio = _make_portfolio_with_position(amount=0.005)

        result = svc.poll_and_reconcile(portfolio)

        assert order_id in ex.cancelled_orders
        assert len(result.cancelled) == 1


# ---------------------------------------------------------------------------
# 7. Dead-letter queue (exchange rejects)
# ---------------------------------------------------------------------------


class TestDeadLetterQueue:
    def test_failed_placement_goes_to_dead_letter(self) -> None:
        ex = _FailingExchangeStub()
        svc, _, db, _nf = _make_service(exchange=ex)
        req = _make_buy_request()
        portfolio = _make_portfolio()

        result = svc.process_order_requests([req], portfolio)

        assert len(result.placed) == 0
        assert len(result.failed) == 1
        assert "connection refused" in result.failed[0].error_reason.lower()
        assert len(db.failed_orders) == 1

    def test_error_notification_sent_on_failure(self) -> None:
        svc, _, _, nf = _make_service(exchange=_FailingExchangeStub())
        svc.process_order_requests([_make_buy_request()], _make_portfolio())
        assert nf.errors, "Expected error notification on placement failure"

    def test_pending_order_marked_rejected_in_db(self) -> None:
        """PENDING order in DB must be updated to REJECTED when exchange fails."""
        svc, _, db, _ = _make_service(exchange=_FailingExchangeStub())
        svc.process_order_requests([_make_buy_request()], _make_portfolio())

        statuses = [o.status for o in db.saved_orders]
        assert OrderStatus.PENDING in statuses
        assert OrderStatus.REJECTED in statuses


# ---------------------------------------------------------------------------
# 8. Precision normalization
# ---------------------------------------------------------------------------


class TestPrecisionNormalization:
    def test_amount_rounded(self) -> None:
        ex = _ExchangeStub()
        svc, _, _, _ = _make_service(exchange=ex)
        req = _make_buy_request(amount=0.0123456789, price=50_000.0)
        portfolio = _make_portfolio()

        svc.process_order_requests([req], portfolio)

        placed_req = ex.created_orders[0]
        assert placed_req.amount == round(0.0123456789, 6)

    def test_limit_price_rounded(self) -> None:
        ex = _ExchangeStub()
        svc, _, _, _ = _make_service(exchange=ex)
        req = _make_buy_request(price=49_999.9876543)
        portfolio = _make_portfolio()

        svc.process_order_requests([req], portfolio)

        placed_req = ex.created_orders[0]
        assert placed_req.price == round(49_999.9876543, 2)

    def test_market_order_no_price_rounding(self) -> None:
        ex = _ExchangeStub()
        svc, _, _, _ = _make_service(exchange=ex)
        req = _make_buy_request(order_type=OrderType.MARKET)
        portfolio = _make_portfolio()

        svc.process_order_requests([req], portfolio)

        placed_req = ex.created_orders[0]
        assert placed_req.price is None


# ---------------------------------------------------------------------------
# 9-12. Order validation
# ---------------------------------------------------------------------------


class TestOrderValidation:
    def test_insufficient_balance_rejected(self) -> None:
        svc, ex, _db, _nf = _make_service()
        req = _make_buy_request(amount=1.0, price=50_000.0)  # costs 50k
        portfolio = _make_portfolio(balance=100.0)  # only 100

        result = svc.process_order_requests([req], portfolio)

        assert len(result.placed) == 0
        assert len(result.failed) == 1
        assert "balance" in result.failed[0].error_reason
        assert len(ex.created_orders) == 0

    def test_sell_without_position_rejected(self) -> None:
        svc, _ex, _, _ = _make_service()
        req = _make_sell_request()
        portfolio = _make_portfolio()

        result = svc.process_order_requests([req], portfolio)

        assert len(result.failed) == 1
        assert "no position" in result.failed[0].error_reason

    def test_sell_exceeds_position_rejected(self) -> None:
        svc, _ex, _, _ = _make_service()
        req = _make_sell_request(amount=1.0)  # selling 1 BTC
        portfolio = _make_portfolio_with_position(amount=0.05)  # only 0.05 BTC

        result = svc.process_order_requests([req], portfolio)

        assert len(result.failed) == 1
        assert "exceeds" in result.failed[0].error_reason

    def test_below_min_amount_rejected(self) -> None:
        class _TightLimitsExchange(_ExchangeStub):
            def get_market_limits(self, symbol: str) -> dict:
                return {"amount_min": 0.1, "cost_min": None, "price_min": None}

        svc, _, _, _ = _make_service(exchange=_TightLimitsExchange())
        req = _make_buy_request(amount=0.0001)  # below 0.1 min
        portfolio = _make_portfolio()

        result = svc.process_order_requests([req], portfolio)

        assert len(result.failed) == 1
        assert "minimum" in result.failed[0].error_reason


# ---------------------------------------------------------------------------
# 13. Save-before-place consistency
# ---------------------------------------------------------------------------


class TestSaveBeforePlace:
    def test_pending_saved_before_exchange_call(self) -> None:
        """PENDING must appear in DB before create_order is called."""
        call_log: list[str] = []

        class _TrackingExchange(_ExchangeStub):
            def create_order(self, request: OrderRequest) -> Order:
                call_log.append("exchange_called")
                return super().create_order(request)

        class _TrackingDB(_DBStub):
            def save_order(self, order: Order) -> None:
                if order.status == OrderStatus.PENDING:
                    call_log.append("pending_saved")
                super().save_order(order)

        svc = ExecutionService(
            exchange_service=_TrackingExchange(),
            db_service=_TrackingDB(),
            notification_service=_NotifStub(),
        )
        svc.process_order_requests([_make_buy_request()], _make_portfolio())

        pending_idx = call_log.index("pending_saved")
        exchange_idx = call_log.index("exchange_called")
        assert pending_idx < exchange_idx, "PENDING must be saved before exchange call"


# ---------------------------------------------------------------------------
# 14-15. LIMIT vs MARKET paths
# ---------------------------------------------------------------------------


class TestOrderTypePaths:
    def test_limit_order_includes_price(self) -> None:
        ex = _ExchangeStub()
        svc, _, _, _ = _make_service(exchange=ex)
        req = _make_buy_request(order_type=OrderType.LIMIT, price=50_000.0)
        portfolio = _make_portfolio()

        svc.process_order_requests([req], portfolio)

        assert ex.created_orders[0].price == round(50_000.0, 2)

    def test_market_order_has_no_price(self) -> None:
        ex = _ExchangeStub()
        svc, _, _, _ = _make_service(exchange=ex)
        req = _make_buy_request(order_type=OrderType.MARKET)
        portfolio = _make_portfolio()

        svc.process_order_requests([req], portfolio)

        assert ex.created_orders[0].price is None


# ---------------------------------------------------------------------------
# 16-18. Portfolio reconciliation math
# ---------------------------------------------------------------------------


class TestPortfolioReconciliationMath:
    def test_buy_fill_updates_balance_and_position(self) -> None:
        """BUY: reconcile correctly replaces tentative reservation with actual fill.

        Phase 3 tentative deducts req.amount * req.price from balance and creates
        a position. _reconcile_fill undoes that and applies the real fill price.
        Net balance effect = -(fill_price * fill_amount + fee).
        """
        ex = _ExchangeStub(paper=True, fill_price=50_500.0)
        svc, _, _, _ = _make_service(exchange=ex)
        req = _make_buy_request(amount=0.01, price=50_000.0)
        initial_balance = 10_000.0
        portfolio = _make_portfolio(balance=initial_balance)

        # Simulate Phase 3 tentative reservation before execution
        _apply_tentative_buy(portfolio, req)

        svc.process_order_requests([req], portfolio)

        pos = portfolio.positions.get(SYMBOL)
        assert pos is not None
        assert abs(pos.amount - 0.01) < 1e-9
        fill_price = 50_500.0
        fee = fill_price * 0.01 * 0.001
        # After undo-then-apply: balance = initial - fill_price * amount - fee
        expected_balance = initial_balance - fill_price * 0.01 - fee
        assert abs(portfolio.balance_quote - expected_balance) < 0.01

    def test_sell_fill_updates_balance_and_removes_position(self) -> None:
        """SELL full: reconcile correctly replaces tentative credit with actual.

        Phase 3 tentative credits ``req.amount * req.price`` to balance and
        removes the position. _reconcile_fill undoes that tentative credit then
        applies the actual fill credit minus fee.  When the position is fully
        sold tentatively, entry_price is lost, so realized_pnl is omitted (only
        the balance is corrected).

        We call _reconcile_fill directly to isolate reconcile math from the
        process_order_requests validation path (which correctly rejects a sell
        when Phase 3 has already tentatively removed the position).
        """
        svc, _, _, _ = _make_service()
        fill_price = 55_000.0
        req = _make_sell_request(amount=0.1, price=55_000.0)
        portfolio = _make_portfolio_with_position(amount=0.1, entry_price=50_000.0, balance=0.0)

        # Pre-apply Phase 3 tentative sell (fully removes position, credits balance)
        _apply_tentative_sell(portfolio, req)
        assert SYMBOL not in portfolio.positions

        # Call _reconcile_fill directly, bypassing Phase 4 validation
        filled_order = _make_filled_order(req, fill_price)
        svc._reconcile_fill(filled_order, portfolio)

        assert SYMBOL not in portfolio.positions
        fee = fill_price * 0.1 * 0.001
        # Net: tentative credit undone, actual credit applied → fill_price * amount - fee
        expected_credit = fill_price * 0.1 - fee
        assert abs(portfolio.balance_quote - expected_credit) < 0.10

    def test_sell_fill_updates_realized_pnl(self) -> None:
        """SELL partial: realized_pnl computed when position remains after tentative.

        Uses a partial sell (0.1 of 0.2 BTC) so Phase 3's tentative only
        reduces the position to 0.1 BTC remaining.  entry_price is still
        available for PnL calculation in _reconcile_fill.

        We call _reconcile_fill directly to isolate reconcile math from the
        process_order_requests validation path.
        """
        svc, _, _, _ = _make_service()
        fill_price = 55_000.0
        req = _make_sell_request(amount=0.1, price=55_000.0)
        # Portfolio holds 0.2 BTC; sell 0.1 so position still exists after tentative
        portfolio = _make_portfolio_with_position(amount=0.2, entry_price=50_000.0, balance=1000.0)

        # Phase 3 tentative partial sell → position reduced to 0.1 BTC
        _apply_tentative_sell(portfolio, req)
        assert abs(portfolio.positions[SYMBOL].amount - 0.1) < 1e-9

        # Call _reconcile_fill directly
        filled_order = _make_filled_order(req, fill_price)
        svc._reconcile_fill(filled_order, portfolio)

        # realized PnL = (55_000 - 50_000) * 0.1 = 500
        assert portfolio.realized_pnl >= 400.0  # allow tolerance for fee treatment
        assert abs(portfolio.positions[SYMBOL].amount - 0.1) < 1e-9  # 0.1 BTC remaining

    def test_incremental_partial_fill_updates_position(self) -> None:
        """Partial fill math: position held at tentative amount, balance corrected.

        With the Phase 3 tentative in place (full 0.01 BTC reserved), a 0.005
        partial fill at the same requested price produces zero price-delta on the
        balance (only the fee is deducted). The position remains at 0.01 BTC
        — the intermediate state that accurately reflects the reserved capital.
        """
        ex = _ExchangeStub(paper=False)
        order_id = "partial-math-1"
        ex._status_responses[order_id] = {
            "status": "partial",
            "filled": 0.005,
            "remaining": 0.005,
            "average": 50_000.0,
        }
        record = _make_db_record(order_id, filled_amount=0.0, requested_amount=0.01, requested_price=50_000.0)
        db = _DBStub()
        db._open_records = [record]
        svc, _, _, _ = _make_service(exchange=ex, db=db)
        portfolio = _make_portfolio()

        # Pre-apply Phase 3 tentative BUY reservation
        _apply_tentative_buy(portfolio, _make_buy_request(amount=0.01, price=50_000.0))

        svc.poll_and_reconcile(portfolio)

        pos = portfolio.positions.get(SYMBOL)
        assert pos is not None
        # Tentative amount remains in position during partial fills
        assert abs(pos.amount - 0.01) < 1e-9


# ---------------------------------------------------------------------------
# 19. Portfolio persistence
# ---------------------------------------------------------------------------


class TestPortfolioPersistence:
    def test_save_portfolio_called_after_poll(self) -> None:
        svc, _, db, _ = _make_service()
        svc.poll_and_reconcile(_make_portfolio())
        assert len(db.saved_portfolios) == 1

    def test_save_portfolio_reflects_updated_state(self) -> None:
        ex = _ExchangeStub(paper=False)
        order_id = "save-port-1"
        ex._status_responses[order_id] = {"status": "closed", "filled": 0.01, "remaining": 0.0, "average": 50_000.0}
        db = _DBStub()
        db._open_records = [_make_db_record(order_id)]
        svc, _, db, _ = _make_service(exchange=ex, db=db)
        portfolio = _make_portfolio()

        svc.poll_and_reconcile(portfolio)

        saved = db.saved_portfolios[-1]
        assert saved is portfolio


# ---------------------------------------------------------------------------
# 20. Notification triggers
# ---------------------------------------------------------------------------


class TestNotificationTriggers:
    def test_placed_notification_sent(self) -> None:
        svc, _, _, nf = _make_service()
        svc.process_order_requests([_make_buy_request()], _make_portfolio())
        assert any("placed" in m.lower() for m in nf.notifications)

    def test_filled_notification_sent(self) -> None:
        svc, _, _, nf = _make_service()
        svc.process_order_requests([_make_buy_request()], _make_portfolio())
        assert any("filled" in m.lower() for m in nf.notifications)

    def test_error_notification_on_failure(self) -> None:
        svc, _, _, nf = _make_service(exchange=_FailingExchangeStub())
        svc.process_order_requests([_make_buy_request()], _make_portfolio())
        assert nf.errors

    def test_cancel_notification_on_stale(self) -> None:
        ex = _ExchangeStub(paper=False)
        oid = "stale-notif-1"
        ex._status_responses[oid] = {"status": "open", "filled": 0.0, "remaining": 0.01, "average": None}
        db = _DBStub()
        db._open_records = [_make_db_record(oid, created_at=datetime.now(UTC) - timedelta(minutes=30))]
        svc, _, _, nf = _make_service(exchange=ex, db=db, stale_minutes=10)
        svc.poll_and_reconcile(_make_portfolio())
        assert any("cancel" in m.lower() or "stale" in m.lower() for m in nf.notifications)


# ---------------------------------------------------------------------------
# 21. Empty order_requests noop
# ---------------------------------------------------------------------------


class TestEmptyOrderRequests:
    def test_empty_list_returns_empty_result(self) -> None:
        svc, ex, db, _ = _make_service()
        result = svc.process_order_requests([], _make_portfolio())
        assert result.placed == []
        assert result.filled == []
        assert result.failed == []
        assert len(ex.created_orders) == 0
        assert len(db.saved_orders) == 0


# ---------------------------------------------------------------------------
# 22. Exchange routing stub
# ---------------------------------------------------------------------------


class TestExchangeRoutingStub:
    def test_select_exchange_returns_configured_id(self) -> None:
        svc, _ex, _, _ = _make_service()
        req = _make_buy_request()
        result = svc._select_exchange(req)
        assert result == EXCHANGE_ID


# ---------------------------------------------------------------------------
# Module-level helper tests
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_normalize_status_closed_to_filled(self) -> None:
        assert _normalize_status("closed") == OrderStatus.FILLED

    def test_normalize_status_partial(self) -> None:
        assert _normalize_status("partial") == OrderStatus.PARTIALLY_FILLED

    def test_normalize_status_canceled(self) -> None:
        assert _normalize_status("canceled") == OrderStatus.CANCELLED

    def test_normalize_status_unknown_defaults_open(self) -> None:
        assert _normalize_status("weird_value") == OrderStatus.OPEN

    def test_failed_order_as_dict(self) -> None:
        req = _make_buy_request()
        fo = FailedOrder(order_request=req, error_reason="test error")
        d = fo.as_dict()
        assert d["symbol"] == SYMBOL
        assert d["error_reason"] == "test error"
        assert "timestamp" in d
