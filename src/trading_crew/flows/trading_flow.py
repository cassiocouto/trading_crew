"""TradingFlow — CrewAI Flow orchestrating a single trading cycle.

Replaces the inline if/else block that lived in main.py's while-loop. Each
cycle is one ``kickoff()``; main.py retains only pre- and post-kickoff
concerns (budget refresh, token accumulation, sleep interval).

Routing summary::

    market_phase() ──► route_after_market()
        ├── "halt"          ──► circuit_breaker_halt()   [terminal]
        ├── "skip_strategy" ──► post_cycle_hooks()
        └── "strategy"      ──► strategy_phase()
                                    └──► route_after_strategy()
                                            ├── "skip_execution" ──► post_cycle_hooks()
                                            └── "execution"      ──► execution_phase()
                                                                        └──► route_after_execution()
                                                                                └──► post_cycle_hooks()
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from crewai.flow.flow import Flow, listen, or_, router, start

from trading_crew.config.settings import (
    ExecutionPipelineMode,
    MarketPipelineMode,
    StrategyPipelineMode,
)
from trading_crew.models.cycle import CycleState

if TYPE_CHECKING:
    from crewai import Crew

    from trading_crew.config.settings import Settings
    from trading_crew.main import BudgetDegradeLevel, BudgetRuntimeState, RunPlan
    from trading_crew.models.market import MarketAnalysis
    from trading_crew.models.order import Order
    from trading_crew.models.portfolio import Portfolio, Position
    from trading_crew.risk.circuit_breaker import CircuitBreaker
    from trading_crew.services.database_service import DatabaseService
    from trading_crew.services.execution_service import ExecutionService
    from trading_crew.services.market_intelligence_service import MarketIntelligenceService
    from trading_crew.services.notification_service import NotificationService
    from trading_crew.services.risk_pipeline import RiskPipeline
    from trading_crew.services.strategy_runner import StrategyRunner

logger = logging.getLogger(__name__)


class TradingFlow(Flow[CycleState]):
    """CrewAI Flow orchestrating a single trading cycle.

    Each instance handles exactly one cycle. Instantiate with all required
    services and call ``kickoff()``; main.py wraps this in the while-loop and
    handles inter-cycle concerns (budget accounting, sleep, shutdown).

    Args:
        cycle_number: Monotonically increasing cycle counter (forwarded to state).
        symbols: Trading pairs for this cycle (forwarded to state).
        plan: Pre-computed run plan with interval/budget flags already applied.
        portfolio: Shared mutable portfolio; modified in-place.
        budget_state: Cross-cycle budget runtime state (read-only inside flow).
        cached_analyses: Most recent market analyses from previous market run,
            used as fallback for stop-loss checks when market phase is skipped.
        circuit_breaker: Portfolio-level circuit breaker (shared reference).
        market_svc: Deterministic market intelligence service.
        strategy_runner: Deterministic strategy evaluation service.
        risk_pipeline: Risk evaluation and order sizing service.
        execution_service: Order placement and polling service.
        db_service: Persistence service.
        notif_service: Notification dispatch service.
        market_crew: Built CrewAI market crew (used in CREWAI/HYBRID mode).
        strategy_crew: Built CrewAI strategy crew (used in CREWAI/HYBRID mode).
        execution_crew: Built CrewAI execution crew (used in CREWAI/HYBRID mode).
        settings: Application settings.
    """

    def __init__(
        self,
        *,
        cycle_number: int,
        symbols: list[str],
        plan: RunPlan,
        portfolio: Portfolio,
        budget_state: BudgetRuntimeState,
        cached_analyses: dict[str, MarketAnalysis],
        circuit_breaker: CircuitBreaker,
        market_svc: MarketIntelligenceService,
        strategy_runner: StrategyRunner,
        risk_pipeline: RiskPipeline,
        execution_service: ExecutionService,
        db_service: DatabaseService,
        notif_service: NotificationService,
        market_crew: Crew,
        strategy_crew: Crew,
        execution_crew: Crew,
        settings: Settings,
    ) -> None:
        # State fields are forwarded to Flow's __init__ which injects them into
        # the CycleState model via **kwargs.
        super().__init__(
            cycle_number=cycle_number,
            symbols=symbols,
            suppress_flow_events=not settings.crewai_verbose,
        )
        self._plan = plan
        self._portfolio = portfolio
        # Snapshot taken just before tentative reservations in strategy_phase();
        # cleared when execution succeeds; used for rollback when skipped/failed.
        self._portfolio_snapshot: Portfolio | None = None
        self._budget_state = budget_state
        self._cached_analyses = cached_analyses
        self._circuit_breaker = circuit_breaker
        self._market_svc = market_svc
        self._strategy_runner = strategy_runner
        self._risk_pipeline = risk_pipeline
        self._execution_service = execution_service
        self._db = db_service
        self._notif = notif_service
        self._market_crew = market_crew
        self._strategy_crew = strategy_crew
        self._execution_crew = execution_crew
        self._settings = settings

    # -------------------------------------------------------------------------
    # Phase methods
    # -------------------------------------------------------------------------

    @start()
    async def market_phase(self) -> None:
        """Run the market intelligence pipeline (deterministic and/or CrewAI)."""
        if not self._plan.run_market:
            logger.info("[1/3] Skipping Market Phase (interval not due)")
            return

        if self._settings.market_pipeline_mode in (
            MarketPipelineMode.DETERMINISTIC,
            MarketPipelineMode.HYBRID,
        ):
            self.state.market_analyses = await self._market_svc.run_cycle(
                symbols=self._settings.symbols,
                timeframe=self._settings.default_timeframe,
                candle_limit=self._settings.market_data_candle_limit,
            )
            logger.info(
                "Market deterministic pipeline completed. Analyses: %d",
                len(self.state.market_analyses),
            )

        if self._settings.market_pipeline_mode in (
            MarketPipelineMode.CREWAI,
            MarketPipelineMode.HYBRID,
        ):
            logger.info("[1/3] Running Market Intelligence Crew...")
            market_result = self._market_crew.kickoff()
            logger.info("Market Crew completed. Raw output length: %d", len(str(market_result)))

        # Apply market data gate: disable strategy/execution when no analyses
        # are available. Only relevant for modes that produce deterministic
        # analyses (CREWAI-only mode skips this since crew output is not parsed
        # into state.market_analyses here).
        if self._settings.market_pipeline_mode != MarketPipelineMode.CREWAI:
            _apply_market_data_gate(self._plan, self.state)

        # Keep position prices current for stop-loss evaluation
        self._update_position_prices()

    @router(market_phase)
    async def route_after_market(self) -> str:
        """Route after market phase.

        Returns:
            "halt"          — circuit breaker tripped; skip all trading
            "skip_strategy" — strategy not due / budget degraded / no data
            "strategy"      — proceed to strategy phase
        """
        if self._circuit_breaker.is_tripped:
            return "halt"
        if not self._plan.run_strategy:
            return "skip_strategy"
        return "strategy"

    @listen("strategy")
    async def strategy_phase(self) -> None:
        """Run the strategy and risk pipeline, building order requests."""
        if self._settings.strategy_pipeline_mode in (
            StrategyPipelineMode.DETERMINISTIC,
            StrategyPipelineMode.HYBRID,
        ):
            # Snapshot taken before tentative reservations so we can roll back
            # if execution is later skipped or fails.
            self._portfolio_snapshot = self._portfolio.model_copy(deep=True)
            try:
                self.state.signals = self._strategy_runner.evaluate(self.state.market_analyses)

                # Pre-fetch break-even prices for all held symbols in one DB
                # round-trip so the risk pipeline stays I/O-free.
                held_symbols = list(self._portfolio.positions.keys())
                break_even_prices: dict[str, float | None] = (
                    self._db.get_break_even_prices(held_symbols) if held_symbols else {}
                )

                for sig in self.state.signals:
                    analysis = self.state.market_analyses.get(sig.symbol)
                    result = self._risk_pipeline.evaluate(
                        sig, self._portfolio, analysis, break_even_prices
                    )
                    self.state.risk_results.append(result)
                    order_req = self._risk_pipeline.to_order_request(sig, result)
                    if order_req is not None:
                        self.state.order_requests.append(order_req)
                        _apply_single_order_to_portfolio(self._portfolio, order_req)
                    self._db.save_signal(sig, risk_verdict=result.verdict.value)

                self._portfolio.update_peak()
                logger.info(
                    "Strategy deterministic pipeline: %d signals, %d risk-approved, "
                    "%d order requests",
                    len(self.state.signals),
                    len([r for r in self.state.risk_results if r.is_approved]),
                    len(self.state.order_requests),
                )
                if self.state.order_requests:
                    logger.info(
                        "Portfolio (tentative): balance=%.2f, positions=%d, exposure=%.1f%%",
                        self._portfolio.balance_quote,
                        len(self._portfolio.positions),
                        self._portfolio.exposure_pct,
                    )
            except Exception:
                logger.exception("Strategy pipeline failed")
                _rollback_portfolio(self._portfolio, self._portfolio_snapshot, self.state)
                self._portfolio_snapshot = None
                self._notif.notify_error("Strategy pipeline failed — reservations rolled back")
                raise  # propagates out of the flow; main.py's except block logs it

        if self._settings.strategy_pipeline_mode in (
            StrategyPipelineMode.CREWAI,
            StrategyPipelineMode.HYBRID,
        ):
            logger.info("[2/3] Running Strategy Crew...")
            strategy_result = self._strategy_crew.kickoff()
            logger.info("Strategy Crew completed. Raw output length: %d", len(str(strategy_result)))

    @router(strategy_phase)
    async def route_after_strategy(self) -> str:
        """Route after strategy phase.

        Returns:
            "skip_execution" — no open orders + no requests / HARD_STOP / interval not due
            "execution"      — proceed to execution phase
        """
        if not self._plan.run_execution:
            return "skip_execution"
        return "execution"

    @listen("execution")
    async def execution_phase(self) -> None:
        """Place new orders and poll existing ones for fills/cancellations."""
        logger.info("[3/3] Running Execution pipeline...")
        try:
            if self._settings.execution_pipeline_mode in (
                ExecutionPipelineMode.DETERMINISTIC,
                ExecutionPipelineMode.HYBRID,
            ):
                exec_result = await self._execution_service.process_order_requests(
                    self.state.order_requests, self._portfolio
                )
                poll_result = await self._execution_service.poll_and_reconcile(self._portfolio)

                self.state.orders = exec_result.placed + poll_result.placed
                self.state.filled_orders = exec_result.filled + poll_result.filled
                self.state.cancelled_orders = exec_result.cancelled + poll_result.cancelled
                # Stored as dicts — see CycleState.failed_orders docstring.
                self.state.failed_orders = [
                    f.as_dict() for f in exec_result.failed + poll_result.failed
                ]

                logger.info(
                    "Execution deterministic pipeline: placed=%d, filled=%d, "
                    "cancelled=%d, failed=%d",
                    len(self.state.orders),
                    len(self.state.filled_orders),
                    len(self.state.cancelled_orders),
                    len(self.state.failed_orders),
                )
                if self.state.filled_orders:
                    logger.info(
                        "Portfolio (post-fill): balance=%.4f, positions=%d, realized_pnl=%.4f",
                        self._portfolio.balance_quote,
                        len(self._portfolio.positions),
                        self._portfolio.realized_pnl,
                    )

            if self._settings.execution_pipeline_mode in (
                ExecutionPipelineMode.CREWAI,
                ExecutionPipelineMode.HYBRID,
            ):
                logger.info("[3/3] Running Execution Crew (CrewAI)...")
                crew_result = self._execution_crew.kickoff()
                logger.info(
                    "Execution Crew completed. Raw output length: %d",
                    len(str(crew_result)),
                )

            # Fills confirmed — snapshot no longer needed for rollback
            self._portfolio_snapshot = None

        except Exception:
            logger.exception("Execution pipeline failed")
            _rollback_portfolio(self._portfolio, self._portfolio_snapshot, self.state)
            self._portfolio_snapshot = None
            self._notif.notify_error("Execution pipeline failed — reservations rolled back")

    @router(execution_phase)
    async def route_after_execution(self) -> str:
        return "post_cycle"

    @listen(or_("skip_strategy", "skip_execution", "post_cycle"))
    async def post_cycle_hooks(self) -> None:
        """Run post-cycle finalisation: rollback, hooks, stop-loss, persistence."""
        # 1. Roll back tentative portfolio reservations when execution was
        #    skipped (snapshot is non-None) or when this path is reached from
        #    the skip_strategy route (no reservations → rollback is a no-op).
        if self._portfolio_snapshot is not None:
            open_orders_label = (
                str(self._plan.open_orders_count)
                if self._plan.open_orders_count is not None
                else "n/a (not checked)"
            )
            logger.info(
                "[3/3] Skipping Execution pipeline (interval not due or no open orders: %s)",
                open_orders_label,
            )
            _rollback_portfolio(self._portfolio, self._portfolio_snapshot, self.state)
            self._portfolio_snapshot = None

            # 2. Hard-stop deterministic poll: even when LLM crews are paused,
            #    keep open orders reconciled at no extra LLM cost.
            if (
                self._budget_state.degrade_level == _hard_stop_level()
                and self._settings.non_llm_monitor_on_hard_stop
            ):
                logger.info("Hard-stop: running deterministic order poll only")
                try:
                    await self._execution_service.poll_and_reconcile(self._portfolio)
                except Exception:
                    logger.exception("Hard-stop order poll failed")

        # 3. Fire per-fill event hooks (CB re-check affects NEXT cycle only)
        for order in self.state.filled_orders:
            self._on_order_filled(order)

        # 4. Stop-loss monitoring
        if self._settings.stop_loss_monitoring_enabled:
            await self._check_stop_losses()

        # 5. Persist cycle summary
        if self._settings.save_cycle_history:
            try:
                self._db.save_cycle_summary(self.state, self._portfolio)
            except Exception:
                logger.exception(
                    "Failed to persist cycle summary for cycle %d",
                    self.state.cycle_number,
                )

        # 6. Persist portfolio state
        try:
            self._db.save_portfolio(self._portfolio)
        except Exception:
            logger.exception("Failed to save portfolio snapshot")

        logger.info(self.state.summary)

    @listen("halt")
    async def circuit_breaker_halt(self) -> None:
        """Terminal handler when the circuit breaker is tripped at cycle start."""
        self.state.circuit_breaker_tripped = True
        self._on_circuit_breaker_activated()

    # -------------------------------------------------------------------------
    # Event hooks (overrideable by subclasses)
    # -------------------------------------------------------------------------

    def _on_order_filled(self, order: Order) -> None:
        """Called for each newly filled order in this cycle.

        Saves a PnL snapshot to the database and re-checks the circuit breaker.
        A trip triggered here takes effect on the *next* cycle because routing
        for the current cycle has already completed.
        """
        try:
            snapshot = self._portfolio.snapshot()
            self._db.save_pnl_snapshot(snapshot)
            logger.info(
                "Order filled: %s %s %s (pnl=%.4f)",
                order.request.side.value,
                order.request.symbol,
                order.id,
                self._portfolio.realized_pnl,
            )
        except Exception:
            logger.exception("_on_order_filled: failed to save PnL snapshot for order %s", order.id)
        # Re-check CB; if tripped, next cycle's _route_after_market returns "halt"
        self._circuit_breaker.check(self._portfolio)

    def _on_circuit_breaker_activated(self) -> None:
        """Called when the market phase router routes to 'halt'.

        Persists the current portfolio state and sends a critical alert.
        """
        logger.critical(
            "Circuit breaker halt: %s. Persisting portfolio and alerting.",
            self._circuit_breaker.trip_reason,
        )
        try:
            self._db.save_portfolio(self._portfolio)
        except Exception:
            logger.exception("_on_circuit_breaker_activated: failed to save portfolio")
        self._notif.notify_error(
            f"CIRCUIT BREAKER TRIPPED — trading halted.\n"
            f"Reason: {self._circuit_breaker.trip_reason}"
        )

    async def _on_stop_loss_triggered(
        self, symbol: str, pos: Position, current_price: float
    ) -> None:
        """Called when a position's stop-loss level has been breached.

        Constructs an immediate MARKET SELL order and submits it through the
        execution service. The tentative sell is applied to the portfolio
        first; execution reconciliation will replace it with the actual fill.
        """
        from trading_crew.models.order import OrderRequest, OrderSide, OrderType

        logger.warning(
            "Stop-loss triggered for %s: current_price=%.4f <= stop_loss=%.4f",
            symbol,
            current_price,
            pos.stop_loss_price,
        )
        req = OrderRequest(
            symbol=symbol,
            exchange=pos.exchange,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            amount=pos.amount,
            strategy_name=pos.strategy_name or "stop_loss",
        )
        _apply_single_order_to_portfolio(self._portfolio, req)
        try:
            sl_result = await self._execution_service.process_order_requests([req], self._portfolio)
            # Append stop-loss orders into cycle state so CycleRecord counts them
            self.state.orders = list(self.state.orders) + sl_result.placed
            self.state.filled_orders = list(self.state.filled_orders) + sl_result.filled
            self.state.failed_orders = list(self.state.failed_orders) + [
                f.as_dict() for f in sl_result.failed
            ]
        except Exception:
            logger.exception("Stop-loss order placement failed for %s", symbol)
        self._notif.notify_error(
            f"Stop-loss triggered for {symbol} @ {current_price:.4f} "
            f"(stop={pos.stop_loss_price:.4f}). SELL order submitted."
        )

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    async def _check_stop_losses(self) -> None:
        """Check all open positions against their stop-loss levels.

        Falls back to ``cached_analyses`` (from the previous market run) when
        the market phase was skipped this cycle, so stop-loss evaluation is
        never completely blind.
        """
        analyses = self.state.market_analyses or self._cached_analyses
        for symbol, pos in list(self._portfolio.positions.items()):
            if pos.stop_loss_price is None:
                continue
            analysis = analyses.get(symbol)
            if analysis is None:
                continue
            current_price = analysis.current_price
            if pos.side == "long" and current_price <= pos.stop_loss_price:
                await self._on_stop_loss_triggered(symbol, pos, current_price)

    def _update_position_prices(self) -> None:
        """Refresh ``current_price`` on all open positions from fresh market data."""
        for symbol, pos in self._portfolio.positions.items():
            analysis = self.state.market_analyses.get(symbol)
            if analysis is not None:
                self._portfolio.positions[symbol] = pos.model_copy(
                    update={"current_price": analysis.current_price}
                )


# ---------------------------------------------------------------------------
# Module-level helpers (imported from main to avoid duplication)
# ---------------------------------------------------------------------------
# These are imported lazily at call time to avoid a circular import between
# trading_flow and main.  The functions are module-level in main.py and have
# no dependency on main's global state, so importing them at runtime is safe.


def _apply_market_data_gate(plan: RunPlan, state: CycleState) -> RunPlan:
    """Delegate to main._apply_market_data_gate (avoids circular import)."""
    from trading_crew.main import _apply_market_data_gate as _gate

    return _gate(plan, state)


def _apply_single_order_to_portfolio(portfolio: Portfolio, req: object) -> None:
    """Delegate to main._apply_single_order_to_portfolio."""
    from trading_crew.main import _apply_single_order_to_portfolio as _apply

    _apply(portfolio, req)  # type: ignore[arg-type]


def _rollback_portfolio(
    portfolio: Portfolio, snapshot: Portfolio | None, state: CycleState
) -> None:
    """Delegate to main._rollback_portfolio."""
    from trading_crew.main import _rollback_portfolio as _rollback

    _rollback(portfolio, snapshot, state)


def _hard_stop_level() -> BudgetDegradeLevel:
    """Return the HARD_STOP enum value (imported lazily)."""
    from trading_crew.main import BudgetDegradeLevel

    return BudgetDegradeLevel.HARD_STOP
