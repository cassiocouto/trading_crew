"""Execution Service — deterministic order placement and lifecycle management.

This is the Phase 4 deterministic pipeline, analogous to
``MarketIntelligenceService`` (Phase 2) and ``StrategyRunner`` (Phase 3).
It handles:

  1. Order validation (balance, min-size, symbol checks)
  2. Precision normalization via CCXT markets metadata
  3. Exchange routing stub (single exchange → multi-exchange ready)
  4. Save-before-place crash safety (PENDING → OPEN | REJECTED)
  5. Immediate fill reconciliation for paper-mode orders
  6. Polling open orders → partial fill state machine → full reconciliation
  7. Stale order cancellation (fully-open and partially-filled)
  8. Portfolio reconciliation (replace tentative Phase 3 reservations with
     actual fill data via undo-then-apply)
  9. Dead-letter queue for placement failures
 10. Structured audit logging and Telegram notifications at every transition
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from trading_crew.models.order import (
    Order,
    OrderFill,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
)

if TYPE_CHECKING:
    from trading_crew.models.portfolio import Portfolio, Position
    from trading_crew.services.database_service import DatabaseService
    from trading_crew.services.exchange_service import ExchangeService
    from trading_crew.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

#: Default taker fee rate used when the exchange does not report fees
#: explicitly in the raw order response (0.1%).
_DEFAULT_FEE_RATE: float = 0.001

#: Mapping of raw exchange status strings to ``OrderStatus`` enum values.
_STATUS_MAP: dict[str, OrderStatus] = {
    "pending": OrderStatus.PENDING,
    "open": OrderStatus.OPEN,
    "partial": OrderStatus.PARTIALLY_FILLED,
    "partially_filled": OrderStatus.PARTIALLY_FILLED,
    "closed": OrderStatus.FILLED,
    "filled": OrderStatus.FILLED,
    "canceled": OrderStatus.CANCELLED,
    "cancelled": OrderStatus.CANCELLED,
    "expired": OrderStatus.CANCELLED,
    "rejected": OrderStatus.REJECTED,
}


# ---------------------------------------------------------------------------
# Protocol for DB record duck typing
# ---------------------------------------------------------------------------


@runtime_checkable
class OrderRecordLike(Protocol):
    """Structural interface expected from DB order records.

    Both the real SQLAlchemy ``OrderRecord`` and plain-Python test stubs
    must expose these attributes for ``ExecutionService`` to operate on them.
    """

    exchange_order_id: str
    symbol: str
    exchange: str
    side: str
    order_type: str
    status: str
    requested_amount: float
    filled_amount: float
    requested_price: float | None
    stop_loss_price: float | None
    take_profit_price: float | None
    strategy_name: str
    created_at: datetime | None


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class FailedOrder:
    """A dead-letter entry for an order that could not be placed."""

    order_request: OrderRequest
    error_reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_dict(self) -> dict:
        return {
            "symbol": self.order_request.symbol,
            "exchange": self.order_request.exchange,
            "side": self.order_request.side.value,
            "order_type": self.order_request.order_type.value,
            "amount": self.order_request.amount,
            "price": self.order_request.price,
            "strategy_name": self.order_request.strategy_name,
            "error_reason": self.error_reason,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ExecutionResult:
    """Structured output of one execution cycle.

    Attributes:
        placed: Orders successfully submitted to the exchange (or simulated).
        filled: Orders that reached FILLED status this cycle.
        cancelled: Orders that were cancelled (stale or error) this cycle.
        failed: Order requests that could not be placed (dead-letter entries).
        errors: Non-fatal error strings for diagnostics.
    """

    placed: list[Order] = field(default_factory=list)
    filled: list[Order] = field(default_factory=list)
    cancelled: list[Order] = field(default_factory=list)
    failed: list[FailedOrder] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# ExecutionService
# ---------------------------------------------------------------------------


class ExecutionService:
    """Deterministic execution pipeline for order placement and monitoring.

    Args:
        exchange_service: CCXT exchange facade for order operations.
        db_service: Persistence layer for orders, portfolio, and failed orders.
        notification_service: Telegram/webhook notifier.
        stale_order_cancel_minutes: Minutes before a fully-open order is stale.
        stale_partial_fill_cancel_minutes: Minutes before a partially-filled
            order is considered stale (longer timeout mirrors silvia_v2's
            6-hour partial fill window).
    """

    def __init__(
        self,
        exchange_service: ExchangeService,
        db_service: DatabaseService,
        notification_service: NotificationService,
        stale_order_cancel_minutes: int = 10,
        stale_partial_fill_cancel_minutes: int = 360,
    ) -> None:
        self._exchange = exchange_service
        self._db = db_service
        self._notif = notification_service
        self._stale_minutes = stale_order_cancel_minutes
        self._stale_partial_minutes = stale_partial_fill_cancel_minutes

    # -- Public API -----------------------------------------------------------

    def process_order_requests(
        self,
        order_requests: list[OrderRequest],
        portfolio: Portfolio,
    ) -> ExecutionResult:
        """Place orders for each risk-approved order request.

        For each request:
          1. Validate (balance, min size, symbol)
          2. Normalize precision
          3. Select target exchange
          4. Save PENDING to DB (crash safety)
          5. Place on exchange
          6. Finalize pending record with real exchange ID (crash safety)
          7. Reconcile fills immediately (paper mode returns FILLED)
          8. Send notifications

        Args:
            order_requests: Risk-approved requests from Phase 3.
                The portfolio is assumed to already have the tentative
                reservations applied by Phase 3's
                ``_apply_single_order_to_portfolio()``.
            portfolio: Current portfolio state (modified in-place on fills).

        Returns:
            ExecutionResult with placed, filled, and failed order lists.
        """
        result = ExecutionResult()

        if not order_requests:
            logger.debug("No order requests to process this cycle")
            return result

        logger.info("Processing %d order request(s)", len(order_requests))

        for req in order_requests:
            self._process_single_request(req, portfolio, result)

        logger.info(
            "Order placement complete: placed=%d, filled=%d, failed=%d",
            len(result.placed),
            len(result.filled),
            len(result.failed),
        )
        return result

    def poll_and_reconcile(self, portfolio: Portfolio) -> ExecutionResult:
        """Poll open orders and reconcile fills / cancel stale orders.

        Fetches all open orders from the DB, checks their exchange status, and:
          - Fully-filled orders: undo tentative reservation → apply actual fill
          - Partially-filled orders: incremental reconcile, keep polling
          - Stale fully-open orders: cancel + release tentative reservation
          - Stale partially-filled orders: cancel + reconcile filled portion

        After reconciliation, persists the updated portfolio to DB.

        Args:
            portfolio: Current portfolio state (modified in-place).
                Tentative Phase 3 reservations are expected to be in place.

        Returns:
            ExecutionResult with filled and cancelled order lists.
        """
        result = ExecutionResult()
        open_records = self._db.get_open_orders()

        if not open_records:
            logger.debug("No open orders to poll")
            self._db.save_portfolio(portfolio)
            return result

        logger.info("Polling %d open order(s)", len(open_records))

        for record in open_records:
            self._poll_single_order(record, portfolio, result)

        if result.filled or result.cancelled:
            logger.info(
                "Poll reconciliation: filled=%d, cancelled=%d",
                len(result.filled),
                len(result.cancelled),
            )

        self._db.save_portfolio(portfolio)
        logger.debug(
            "Portfolio persisted: balance=%.4f, positions=%d",
            portfolio.balance_quote,
            len(portfolio.positions),
        )
        return result

    # -- Order Request Processing ---------------------------------------------

    def _process_single_request(
        self,
        req: OrderRequest,
        portfolio: Portfolio,
        result: ExecutionResult,
    ) -> None:
        """Handle one order request through the full placement pipeline."""
        # 1. Validate
        valid, reason = self._validate_order(req, portfolio)
        if not valid:
            logger.warning(
                "Order rejected (validation): %s %s %.6f — %s",
                req.side.value,
                req.symbol,
                req.amount,
                reason,
            )
            failed = FailedOrder(order_request=req, error_reason=f"validation: {reason}")
            result.failed.append(failed)
            self._db.save_failed_order(req, failed.error_reason)
            self._notif.notify_error(
                f"Order rejected ({req.symbol} {req.side.value}): {reason}"
            )
            return

        # 2. Normalize precision
        normalized_req = self._normalize_precision(req)

        # 3. Select exchange (routing stub)
        _exchange_id = self._select_exchange(normalized_req)

        # 4. Save PENDING to DB before submission (crash safety)
        pending_order = self._make_pending_order(normalized_req)
        self._db.save_order(pending_order)
        logger.debug(
            "Saved PENDING order %s: %s %s %.6f @ %s",
            pending_order.id,
            normalized_req.side.value,
            normalized_req.symbol,
            normalized_req.amount,
            normalized_req.price or "MARKET",
        )

        # 5. Place on exchange
        try:
            order = self._exchange.create_order(normalized_req)
        except Exception as exc:
            error_msg = str(exc)
            logger.error(
                "Order placement failed: %s %s — %s",
                normalized_req.symbol,
                normalized_req.side.value,
                error_msg,
                exc_info=True,
            )
            # Update DB: mark the PENDING record as REJECTED (no orphan)
            rejected = pending_order.model_copy(
                update={"status": OrderStatus.REJECTED, "updated_at": datetime.now(UTC)}
            )
            self._db.save_order(rejected)

            failed = FailedOrder(order_request=normalized_req, error_reason=error_msg)
            result.failed.append(failed)
            self._db.save_failed_order(normalized_req, error_msg)
            self._notif.notify_error(
                f"Order placement failed ({normalized_req.symbol} "
                f"{normalized_req.side.value}): {error_msg[:200]}"
            )
            return

        # 6. Finalize pending record: update exchange_order_id + status in DB
        #    This ensures we never have an orphaned PENDING record: the pre-placed
        #    record is promoted to the real exchange ID.
        self._db.finalize_pending_order(pending_order.id, order)

        result.placed.append(order)

        logger.info(
            "order.placed: id=%s symbol=%s side=%s type=%s amount=%.6f price=%s "
            "status=%s paper=%s ts=%s",
            order.id,
            normalized_req.symbol,
            normalized_req.side.value,
            normalized_req.order_type.value,
            normalized_req.amount,
            normalized_req.price or "MARKET",
            order.status.value,
            self._exchange.is_paper,
            datetime.now(UTC).isoformat(),
        )

        self._notif.notify(
            f"Order placed: {normalized_req.side.value.upper()} "
            f"{normalized_req.amount:.6f} {normalized_req.symbol} "
            f"({'paper' if self._exchange.is_paper else 'live'})"
        )

        # 7. Immediate reconciliation for terminal orders (paper mode fills instantly)
        if order.status.is_terminal:
            if order.status == OrderStatus.FILLED:
                self._reconcile_fill(order, portfolio)
                result.filled.append(order)
                self._db.save_order(order)
                logger.info(
                    "order.filled: id=%s symbol=%s amount=%.6f avg_price=%.4f fee=%.6f ts=%s",
                    order.id,
                    normalized_req.symbol,
                    order.filled_amount,
                    order.average_fill_price or 0.0,
                    order.total_fee,
                    datetime.now(UTC).isoformat(),
                )
                self._notif.notify(
                    f"Order filled: {normalized_req.side.value.upper()} "
                    f"{order.filled_amount:.6f} {normalized_req.symbol} "
                    f"@ {order.average_fill_price:.4f}"
                )
            elif order.status == OrderStatus.REJECTED:
                logger.warning(
                    "order.rejected: id=%s symbol=%s — exchange rejected order",
                    order.id,
                    normalized_req.symbol,
                )
                failed = FailedOrder(
                    order_request=normalized_req,
                    error_reason="exchange rejected order",
                )
                result.failed.append(failed)
                self._db.save_failed_order(normalized_req, "exchange rejected order")
                self._notif.notify_error(
                    f"Order rejected by exchange: {normalized_req.symbol} "
                    f"{normalized_req.side.value}"
                )

    def _poll_single_order(
        self,
        record: object,
        portfolio: Portfolio,
        result: ExecutionResult,
    ) -> None:
        """Poll status of one open order and apply any transitions."""
        if not isinstance(record, OrderRecordLike):
            return

        order_id = record.exchange_order_id
        symbol = record.symbol
        current_filled = record.filled_amount or 0.0
        created_at = record.created_at or datetime.now(UTC)

        try:
            raw = self._exchange.fetch_order_status(order_id, symbol)
        except Exception as exc:
            logger.error(
                "Failed to poll order %s (%s): %s",
                order_id,
                symbol,
                exc,
                exc_info=True,
            )
            result.errors.append(f"poll failed: {order_id}: {exc}")
            return

        raw_status = str(raw.get("status", "open")).lower()
        new_status = _normalize_status(raw_status)
        exchange_filled = float(raw.get("filled") or 0)
        avg_price = float(raw.get("average") or raw.get("price") or 0)

        now = datetime.now(UTC)
        # Ensure created_at is timezone-aware before computing age
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        age_minutes = (now - created_at).total_seconds() / 60

        # -- Full fill ---
        if new_status == OrderStatus.FILLED:
            order = _build_order_from_record(record, new_status, exchange_filled, avg_price)
            self._reconcile_fill(order, portfolio)
            self._db.save_order(order)
            self._db.update_order_status_by_exchange_id(order_id, OrderStatus.FILLED.value)
            result.filled.append(order)
            logger.info(
                "order.filled: id=%s symbol=%s amount=%.6f avg_price=%.4f ts=%s",
                order_id,
                symbol,
                exchange_filled,
                avg_price,
                now.isoformat(),
            )
            self._notif.notify(
                f"Order filled: {record.side.upper()} {exchange_filled:.6f} "
                f"{symbol} @ {avg_price:.4f}"
            )
            return

        # -- Partial fill delta ---
        if new_status == OrderStatus.PARTIALLY_FILLED and exchange_filled > current_filled:
            delta = exchange_filled - current_filled
            self._reconcile_incremental_fill(
                order_id=order_id,
                symbol=symbol,
                side=record.side,
                delta_amount=delta,
                fill_price=avg_price,
                portfolio=portfolio,
                requested_price=record.requested_price or 0.0,
            )
            self._db.update_order_status_by_exchange_id(order_id, OrderStatus.PARTIALLY_FILLED.value)
            logger.info(
                "order.partially_filled: id=%s symbol=%s delta=%.6f total_filled=%.6f price=%.4f ts=%s",
                order_id,
                symbol,
                delta,
                exchange_filled,
                avg_price,
                now.isoformat(),
            )
            self._notif.notify(
                f"Partial fill: {record.side.upper()} +{delta:.6f} {symbol} "
                f"@ {avg_price:.4f} (total filled: {exchange_filled:.6f})"
            )
            # Check if partial fill has gone stale
            if age_minutes >= self._stale_partial_minutes:
                self._cancel_stale_order(
                    order_id=order_id,
                    symbol=symbol,
                    record=record,
                    portfolio=portfolio,
                    result=result,
                    partially_filled_amount=exchange_filled,
                    avg_fill_price=avg_price,
                    stale_type="partial",
                )
            return

        # -- Stale fully-open order ---
        if new_status in (OrderStatus.OPEN, OrderStatus.PENDING) and age_minutes >= self._stale_minutes:
            self._cancel_stale_order(
                order_id=order_id,
                symbol=symbol,
                record=record,
                portfolio=portfolio,
                result=result,
                partially_filled_amount=0.0,
                avg_fill_price=0.0,
                stale_type="open",
            )
            return

        # -- Already terminal on exchange (cancelled / rejected) ---
        if new_status in (OrderStatus.CANCELLED, OrderStatus.REJECTED):
            self._db.update_order_status_by_exchange_id(order_id, new_status.value)
            self._release_reservation(record, portfolio, filled_amount=exchange_filled)
            order = _build_order_from_record(record, new_status, exchange_filled, avg_price)
            result.cancelled.append(order)
            logger.info(
                "order.%s: id=%s symbol=%s (detected on exchange) ts=%s",
                new_status.value,
                order_id,
                symbol,
                now.isoformat(),
            )

    # -- Stale Order Cancellation ---------------------------------------------

    def _cancel_stale_order(
        self,
        order_id: str,
        symbol: str,
        record: object,
        portfolio: Portfolio,
        result: ExecutionResult,
        partially_filled_amount: float,
        avg_fill_price: float,
        stale_type: str,
    ) -> None:
        """Cancel a stale order, reconcile any filled portion, release remainder."""
        if not isinstance(record, OrderRecordLike):
            return

        try:
            self._exchange.cancel_order(order_id, symbol)
        except Exception as exc:
            logger.error(
                "Failed to cancel stale order %s (%s): %s",
                order_id,
                symbol,
                exc,
                exc_info=True,
            )
            result.errors.append(f"cancel failed: {order_id}: {exc}")
            return

        self._db.update_order_status_by_exchange_id(order_id, OrderStatus.CANCELLED.value)

        # Release the unfilled portion's portfolio reservation
        self._release_reservation(record, portfolio, filled_amount=partially_filled_amount)

        order = _build_order_from_record(
            record, OrderStatus.CANCELLED, partially_filled_amount, avg_fill_price
        )
        result.cancelled.append(order)

        logger.warning(
            "order.cancelled (stale %s): id=%s symbol=%s filled=%.6f ts=%s",
            stale_type,
            order_id,
            symbol,
            partially_filled_amount,
            datetime.now(UTC).isoformat(),
        )
        self._notif.notify(
            f"Stale order cancelled ({stale_type}): {record.side.upper()} "
            f"{record.requested_amount:.6f} {symbol} — "
            f"{partially_filled_amount:.6f} filled before cancellation"
        )

    # -- Portfolio Reconciliation ---------------------------------------------

    def _reconcile_fill(self, order: Order, portfolio: Portfolio) -> None:
        """Replace tentative Phase 3 reservation with actual fill data.

        Phase 3's ``_apply_single_order_to_portfolio()`` books a tentative
        reservation before execution:
          - BUY: deducted ``req.amount * req.price`` from balance and added
            ``req.amount`` to the position.
          - SELL: credited ``req.amount * req.price`` to balance and reduced
            (or deleted) the position by ``req.amount``.

        This method corrects the portfolio from tentative to actual using an
        **undo-then-apply** pattern:
          1. Reverse the tentative booking (restore pre-Phase-3 state).
          2. Apply the real fill (actual amount, price, exchange fee).

        Args:
            order: The placed order with actual fill data.
            portfolio: Portfolio that still has tentative reservation in place.
        """
        from trading_crew.models.portfolio import Position

        req = order.request
        fill_price = order.average_fill_price or req.price or 0.0
        fill_amount = order.filled_amount
        fee = order.total_fee
        tentative_price = req.price or fill_price
        tentative_amount = req.amount

        if req.side == OrderSide.BUY:
            # -- Step 1: Undo tentative BUY -----------------------------------
            # Refund the cash Phase 3 locked for this order
            portfolio.balance_quote += tentative_amount * tentative_price
            # Remove the tentative position contribution
            if req.symbol in portfolio.positions:
                pos = portfolio.positions[req.symbol]
                remaining_after_undo = pos.amount - tentative_amount
                if remaining_after_undo <= 1e-10:
                    del portfolio.positions[req.symbol]
                else:
                    portfolio.positions[req.symbol] = pos.model_copy(
                        update={"amount": remaining_after_undo}
                    )

            # -- Step 2: Apply actual fill ------------------------------------
            portfolio.balance_quote -= fill_amount * fill_price + fee

            if req.symbol in portfolio.positions:
                pos = portfolio.positions[req.symbol]
                total = pos.amount + fill_amount
                new_entry = (pos.entry_price * pos.amount + fill_price * fill_amount) / total
                portfolio.positions[req.symbol] = pos.model_copy(
                    update={
                        "amount": total,
                        "entry_price": new_entry,
                        "current_price": fill_price,
                        "stop_loss_price": req.stop_loss_price or pos.stop_loss_price,
                        "take_profit_price": req.take_profit_price or pos.take_profit_price,
                    }
                )
            else:
                portfolio.positions[req.symbol] = Position(
                    symbol=req.symbol,
                    exchange=req.exchange,
                    entry_price=fill_price,
                    amount=fill_amount,
                    current_price=fill_price,
                    stop_loss_price=req.stop_loss_price,
                    take_profit_price=req.take_profit_price,
                    strategy_name=req.strategy_name,
                )

        elif req.side == OrderSide.SELL:
            # -- Step 1: Undo tentative SELL ----------------------------------
            # Claw back the tentative credit
            tentative_credit = tentative_amount * tentative_price
            portfolio.balance_quote -= tentative_credit

            # Restore the tentative position reduction so we have a clean slate
            # for the actual fill calculation.
            position_for_pnl: Position | None = None
            if req.symbol in portfolio.positions:
                # Partial sell: restore tentative reduction to get full position back
                pos = portfolio.positions[req.symbol]
                restored = pos.model_copy(update={"amount": pos.amount + tentative_amount})
                portfolio.positions[req.symbol] = restored
                position_for_pnl = restored
            else:
                # Full sell: tentative deleted the position — entry_price is lost.
                # We can still apply the correct balance delta; realized_pnl is
                # omitted with a warning (acceptable trade-off vs. data model changes).
                logger.warning(
                    "reconcile_fill: SELL tentative fully deleted %s position; "
                    "realized_pnl will not be recorded for this fill",
                    req.symbol,
                )

            # -- Step 2: Apply actual fill ------------------------------------
            actual_credit = fill_amount * fill_price
            portfolio.balance_quote += actual_credit - fee

            if position_for_pnl is not None:
                entry_price = position_for_pnl.entry_price
                realized_pnl = (fill_price - entry_price) * fill_amount
                portfolio.realized_pnl += realized_pnl
                remaining = position_for_pnl.amount - fill_amount
                if remaining <= 1e-10:
                    del portfolio.positions[req.symbol]
                else:
                    portfolio.positions[req.symbol] = position_for_pnl.model_copy(
                        update={"amount": remaining}
                    )
            # else: position already cleaned up by tentative; nothing more to adjust

        portfolio.total_fees += fee

        logger.debug(
            "portfolio.reconciled: symbol=%s side=%s amount=%.6f price=%.4f fee=%.6f "
            "balance=%.4f positions=%d",
            req.symbol,
            req.side.value,
            fill_amount,
            fill_price,
            fee,
            portfolio.balance_quote,
            len(portfolio.positions),
        )

    def _reconcile_incremental_fill(
        self,
        order_id: str,
        symbol: str,
        side: str,
        delta_amount: float,
        fill_price: float,
        portfolio: Portfolio,
        requested_price: float = 0.0,
    ) -> None:
        """Apply only the incremental delta from a partial fill.

        Called when ``PARTIALLY_FILLED`` is detected with a higher
        ``filled`` amount than previously recorded.

        **Tentative-aware mode** (``requested_price > 0``):
            Phase 3's reservation already placed the full order amount in the
            portfolio (position created, balance deducted at ``requested_price``).
            Only the balance is adjusted here — correcting from tentative price
            to actual fill price and charging the fee. The position itself is
            unchanged; the final ``_reconcile_fill`` will apply the full undo-
            then-apply correction when the order completes.

        **Additive mode** (``requested_price == 0``, e.g. MARKET orders or
            direct calls without tentative context):
            Position and balance are both updated directly for the delta.
        """
        from trading_crew.models.portfolio import Position

        fee = fill_price * delta_amount * _DEFAULT_FEE_RATE
        tentative_mode = requested_price > 0

        if side == OrderSide.BUY.value:
            if tentative_mode:
                # Tentative already holds the full position; only correct balance
                # for price deviation (tentative price vs actual fill) and fee.
                balance_delta = delta_amount * (requested_price - fill_price) - fee
                portfolio.balance_quote += balance_delta
            else:
                # No tentative — add position and deduct balance for the delta.
                if symbol in portfolio.positions:
                    pos = portfolio.positions[symbol]
                    total = pos.amount + delta_amount
                    new_entry = (pos.entry_price * pos.amount + fill_price * delta_amount) / total
                    portfolio.positions[symbol] = pos.model_copy(
                        update={"amount": total, "entry_price": new_entry, "current_price": fill_price}
                    )
                else:
                    portfolio.positions[symbol] = Position(
                        symbol=symbol,
                        exchange=self._exchange.exchange_id,
                        entry_price=fill_price,
                        amount=delta_amount,
                        current_price=fill_price,
                    )
                    portfolio.balance_quote -= fill_price * delta_amount
                portfolio.balance_quote -= fee

        elif side == OrderSide.SELL.value:
            if tentative_mode:
                # Tentative already reduced/removed the position and credited
                # balance at requested_price. Correct for actual vs tentative price.
                balance_delta = delta_amount * (fill_price - requested_price) - fee
                portfolio.balance_quote += balance_delta
                # Realized PnL: position may have been deleted by tentative, so
                # entry_price may be unavailable. Defer to _reconcile_fill on full fill.
            else:
                sell_notional = fill_price * delta_amount
                if symbol in portfolio.positions:
                    pos = portfolio.positions[symbol]
                    realized = (fill_price - pos.entry_price) * delta_amount
                    remaining = pos.amount - delta_amount
                    if remaining <= 1e-10:
                        del portfolio.positions[symbol]
                    else:
                        portfolio.positions[symbol] = pos.model_copy(update={"amount": remaining})
                    portfolio.realized_pnl += realized
                portfolio.balance_quote += sell_notional - fee

        portfolio.total_fees += fee

    def _release_reservation(
        self,
        record: object,
        portfolio: Portfolio,
        filled_amount: float,
    ) -> None:
        """Reverse the tentative Phase 3 reservation for the unfilled portion.

        Called when an order is cancelled (stale or otherwise) before filling.
        Releases only the unfilled portion from portfolio.
        """
        if not isinstance(record, OrderRecordLike):
            return

        symbol = record.symbol
        side = record.side
        requested_amount = record.requested_amount or 0.0
        requested_price = record.requested_price or 0.0

        unfilled = max(0.0, requested_amount - filled_amount)
        if unfilled <= 0:
            return

        unfilled_notional = unfilled * requested_price

        if side == OrderSide.BUY.value:
            # Return the reserved cash for the unfilled portion
            portfolio.balance_quote += unfilled_notional
            # Reduce position by unfilled amount if it exists
            if symbol in portfolio.positions:
                pos = portfolio.positions[symbol]
                remaining = pos.amount - unfilled
                if remaining <= 1e-10:
                    del portfolio.positions[symbol]
                else:
                    portfolio.positions[symbol] = pos.model_copy(update={"amount": remaining})
        elif side == OrderSide.SELL.value:
            # Return the unfilled sell amount to the position
            if symbol in portfolio.positions:
                pos = portfolio.positions[symbol]
                portfolio.positions[symbol] = pos.model_copy(
                    update={"amount": pos.amount + unfilled}
                )
            # Deduct the tentatively credited cash
            portfolio.balance_quote = max(0.0, portfolio.balance_quote - unfilled_notional)

        logger.debug(
            "reservation.released: symbol=%s side=%s unfilled=%.6f notional=%.4f",
            symbol,
            side,
            unfilled,
            unfilled_notional,
        )

    # -- Validation & Precision -----------------------------------------------

    def _validate_order(
        self, req: OrderRequest, portfolio: Portfolio
    ) -> tuple[bool, str]:
        """Validate an order request against balance and exchange constraints.

        For MARKET BUY orders the current ask price is fetched from the exchange
        to estimate cost; if the ticker is unavailable the balance check is
        skipped rather than blocking the order.

        Returns:
            ``(valid, reason)`` — if ``valid`` is False, ``reason`` explains why.
        """
        price = req.price or 0.0

        # For MARKET BUY orders estimate the cost from the current ask price
        if req.order_type == OrderType.MARKET and req.side == OrderSide.BUY:
            try:
                ticker = self._exchange.fetch_ticker(req.symbol)
                price = ticker.ask if ticker.ask > 0 else ticker.last
            except Exception as exc:
                logger.debug(
                    "Could not fetch ticker for MARKET order validation (%s): %s — skipping balance check",
                    req.symbol,
                    exc,
                )
                price = 0.0  # skip balance check when price is unavailable

        notional = req.amount * price if price > 0 else 0.0

        # Balance check for BUY orders (collapsed per SIM102)
        if req.side == OrderSide.BUY and price > 0 and notional > portfolio.balance_quote:
            return (
                False,
                f"insufficient balance: need {notional:.4f}, have {portfolio.balance_quote:.4f}",
            )

        # SELL: ensure position exists
        if req.side == OrderSide.SELL:
            pos = portfolio.positions.get(req.symbol)
            if pos is None:
                return False, f"no position to sell for {req.symbol}"
            if req.amount > pos.amount:
                return (
                    False,
                    f"sell amount {req.amount:.6f} exceeds position {pos.amount:.6f}",
                )

        # Exchange min-size constraints
        try:
            limits = self._exchange.get_market_limits(req.symbol)
            amount_min = limits.get("amount_min")
            cost_min = limits.get("cost_min")

            if amount_min is not None and req.amount < amount_min:
                return (
                    False,
                    f"amount {req.amount:.6f} below exchange minimum {amount_min:.6f}",
                )
            if cost_min is not None and notional > 0 and notional < cost_min:
                return (
                    False,
                    f"cost {notional:.4f} below exchange minimum {cost_min:.4f}",
                )
        except Exception as exc:
            # Market limit lookup failed — log but don't block the order
            logger.debug("Could not check market limits for %s: %s", req.symbol, exc)

        return True, ""

    def _normalize_precision(self, req: OrderRequest) -> OrderRequest:
        """Round amount and price to exchange-required precision.

        Returns a new ``OrderRequest`` with rounded values if markets are
        loaded; otherwise returns the original request unchanged.
        """
        try:
            rounded_amount, rounded_price = self._exchange.normalize_order_precision(
                req.symbol, req.amount, req.price
            )
            if rounded_amount != req.amount or rounded_price != req.price:
                logger.debug(
                    "precision.normalized: symbol=%s amount=%.8f->%.8f price=%s->%s",
                    req.symbol,
                    req.amount,
                    rounded_amount,
                    req.price,
                    rounded_price,
                )
                return req.model_copy(update={"amount": rounded_amount, "price": rounded_price})
        except Exception as exc:
            logger.debug(
                "precision normalization failed for %s: %s — using raw values",
                req.symbol,
                exc,
            )
        return req

    # -- Exchange Routing -----------------------------------------------------

    def _select_exchange(self, req: OrderRequest) -> str:
        """Select the target exchange for an order request.

        Currently returns the configured exchange ID. This stub interface is
        designed to support future best-bid/ask routing when multiple exchange
        connections are configured (compare ticker ask/bid across exchanges
        and route to the most favourable price).

        Args:
            req: The order request to route.

        Returns:
            Exchange ID string (e.g. ``"binance"``).
        """
        return self._exchange.exchange_id

    # -- Helpers --------------------------------------------------------------

    @staticmethod
    def _make_pending_order(req: OrderRequest) -> Order:
        """Create a placeholder Order with PENDING status for save-before-place."""
        return Order(
            id=f"pending-{uuid.uuid4().hex[:12]}",
            request=req,
            status=OrderStatus.PENDING,
            filled_amount=0.0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _normalize_status(raw: str) -> OrderStatus:
    """Map an exchange/raw status string to an ``OrderStatus`` enum value."""
    return _STATUS_MAP.get(raw.lower(), OrderStatus.OPEN)


def _build_order_from_record(
    record: object,
    status: OrderStatus,
    filled_amount: float,
    avg_price: float,
) -> Order:
    """Reconstruct a minimal Order domain object from a DB record.

    Works with both the real SQLAlchemy ``OrderRecord`` and test stubs that
    expose the same attribute interface (duck typing via ``OrderRecordLike``).
    """
    if not isinstance(record, OrderRecordLike):
        raise TypeError(f"Expected an OrderRecordLike, got {type(record)}")

    req = OrderRequest(
        symbol=record.symbol,
        exchange=record.exchange,
        side=OrderSide(record.side),
        order_type=OrderType(record.order_type),
        amount=record.requested_amount or 0.0,
        price=record.requested_price,
        stop_loss_price=record.stop_loss_price,
        take_profit_price=record.take_profit_price,
        strategy_name=record.strategy_name or "",
    )
    fill = None
    if filled_amount > 0 and avg_price > 0:
        fee_currency = record.symbol.split("/")[1] if "/" in record.symbol else "USDT"
        fill = OrderFill(
            price=avg_price,
            amount=filled_amount,
            fee=avg_price * filled_amount * _DEFAULT_FEE_RATE,
            fee_currency=fee_currency,
            timestamp=datetime.now(UTC),
        )

    return Order(
        id=record.exchange_order_id,
        request=req,
        status=status,
        filled_amount=filled_amount,
        average_fill_price=avg_price if avg_price > 0 else None,
        fills=[fill] if fill else [],
        created_at=record.created_at or datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
