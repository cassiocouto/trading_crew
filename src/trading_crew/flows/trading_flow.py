"""TradingFlow — CrewAI Flow orchestrating a single trading cycle.

Deterministic-first architecture: the pipeline always runs deterministically,
and the advisory crew activates only when the uncertainty score exceeds the
configured threshold.

Routing summary::

    market_phase() ──► route_after_market()
        ├── "halt"           ──► circuit_breaker_halt()          [terminal]
        ├── "execution_only" ──► execution_only_phase()  ──► post_cycle_hooks()
        ├── "skip_strategy"  ──► post_cycle_hooks()
        └── "strategy"       ──► strategy_phase()  [signals + risk eval, NO portfolio mutation]
                                    └──► compute_uncertainty()
                                            └──► route_after_uncertainty()
                                                    ├── "skip_advisory" ──► reserve_phase()
                                                    └── "advisory"      ──► advisory_phase()
                                                                                └──► reserve_phase()
                                                    reserve_phase()
                                        └──► route_after_reserve()
                                                ├── "skip_execution" ──► post_cycle_hooks()
                                                └── "execution"      ──► execution_phase()
                                                                            └──► post_cycle_hooks()
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from crewai.flow.flow import Flow, listen, or_, router, start

from trading_crew.models.advisory import apply_advisory_directives
from trading_crew.models.cycle import CycleState

if TYPE_CHECKING:
    from trading_crew.config.settings import Settings
    from trading_crew.crews.advisory_crew import AdvisoryCrew
    from trading_crew.main import BudgetRuntimeState, RunPlan
    from trading_crew.models.market import MarketAnalysis
    from trading_crew.models.order import Order, OrderRequest
    from trading_crew.models.portfolio import Portfolio, Position
    from trading_crew.models.signal import StrategyEvaluation
    from trading_crew.risk.circuit_breaker import CircuitBreaker
    from trading_crew.services.database_service import DatabaseService
    from trading_crew.services.execution_service import ExecutionService
    from trading_crew.services.market_intelligence_service import MarketIntelligenceService
    from trading_crew.services.notification_service import NotificationService
    from trading_crew.services.risk_pipeline import RiskPipeline
    from trading_crew.services.strategy_runner import StrategyRunner
    from trading_crew.services.uncertainty_scorer import UncertaintyResult, UncertaintyScorer

logger = logging.getLogger(__name__)


class TradingFlow(Flow[CycleState]):
    """CrewAI Flow orchestrating a single trading cycle.

    Each instance handles exactly one cycle. Instantiate with all required
    services and call ``kickoff()``; main.py wraps this in the while-loop and
    handles inter-cycle concerns (budget accounting, sleep, shutdown).

    Args:
        cycle_number: Monotonically increasing cycle counter.
        symbols: Trading pairs for this cycle.
        plan: Pre-computed run plan with interval/budget flags.
        portfolio: Shared mutable portfolio; modified in-place.
        budget_state: Cross-cycle budget runtime state (read-only inside flow).
        cached_analyses: Fallback analyses from previous market run.
        circuit_breaker: Portfolio-level circuit breaker.
        market_svc: Deterministic market intelligence service.
        strategy_runner: Deterministic strategy evaluation service.
        risk_pipeline: Risk evaluation and order sizing service.
        execution_service: Order placement and polling service.
        db_service: Persistence service.
        notif_service: Notification dispatch service.
        uncertainty_scorer: Deterministic uncertainty scoring service.
        advisory_crew: Optional advisory crew (None when advisory is disabled).
        previous_regimes: Regime per symbol from the prior cycle.
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
        uncertainty_scorer: UncertaintyScorer,
        advisory_crew: AdvisoryCrew | None = None,
        previous_regimes: dict[str, str] | None = None,
        settings: Settings,
    ) -> None:
        super().__init__(
            cycle_number=cycle_number,
            symbols=symbols,
            suppress_flow_events=not settings.crewai_verbose,
        )
        self._plan = plan
        self._portfolio = portfolio
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
        self._uncertainty_scorer = uncertainty_scorer
        self._advisory_crew = advisory_crew
        self._previous_regimes = previous_regimes or {}
        self._settings = settings
        self._evaluation: StrategyEvaluation | None = None
        self._uncertainty_result: UncertaintyResult | None = None

    # -------------------------------------------------------------------------
    # Phase methods
    # -------------------------------------------------------------------------

    @start()
    async def market_phase(self) -> None:
        """Run the deterministic market intelligence pipeline.

        Note: ``run_market`` is currently always True in ``_build_run_plan``.
        The guard is kept for forward-compatibility if market skipping is added.
        """
        if not self._plan.run_market:
            logger.info("[market] Skipping (interval not due)")
            return

        self.state.market_analyses = await self._market_svc.run_cycle(
            symbols=self._settings.symbols,
            timeframe=self._settings.default_timeframe,
            candle_limit=self._settings.market_data_candle_limit,
        )
        logger.info(
            "Market pipeline completed. Analyses: %d",
            len(self.state.market_analyses),
        )

        _apply_market_data_gate(self._plan, self.state)
        self._update_position_prices()

    @router(market_phase)
    async def route_after_market(self) -> str:
        if self._circuit_breaker.is_tripped:
            return "halt"
        if not self._plan.run_strategy:
            if self._plan.run_execution:
                return "execution_only"
            return "skip_strategy"
        return "strategy"

    @listen("strategy")
    async def strategy_phase(self) -> None:
        """Generate signals and run risk evaluation — NO portfolio mutation."""
        try:
            self._evaluation = self._strategy_runner.evaluate(self.state.market_analyses)
            self.state.signals = self._evaluation.signals

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
                self._db.save_signal(sig, risk_verdict=result.verdict.value)

            logger.info(
                "Strategy pipeline: %d signals, %d risk-approved, %d order requests",
                len(self.state.signals),
                len([r for r in self.state.risk_results if r.is_approved]),
                len(self.state.order_requests),
            )
        except Exception:
            logger.exception("Strategy pipeline failed")
            self._notif.notify_error("Strategy pipeline failed")
            raise

    @listen(strategy_phase)
    async def compute_uncertainty(self) -> None:
        """Compute the uncertainty score from deterministic pipeline output."""
        votes = self._evaluation.votes if self._evaluation else {}
        sentiment = getattr(self._market_svc, "last_sentiment", None)

        uncertainty = self._uncertainty_scorer.score(
            analyses=self.state.market_analyses,
            votes=votes,
            portfolio=self._portfolio,
            risk_params=self._settings.risk,
            sentiment=sentiment,
            previous_regimes=self._previous_regimes,
        )

        self.state.uncertainty_score = uncertainty.score
        self.state.uncertainty_factors = [
            f"{f.name}={f.raw_value:.3f}(w={f.weighted_contribution:.3f})"
            for f in uncertainty.factors
            if f.weighted_contribution > 0
        ]
        self._uncertainty_result = uncertainty

        logger.info(
            "Uncertainty score: %.3f (threshold: %.2f, recommend_advisory: %s)",
            uncertainty.score,
            self._settings.advisory_activation_threshold,
            uncertainty.recommend_advisory,
        )

    @router(compute_uncertainty)
    async def route_after_uncertainty(self) -> str:
        result = self._uncertainty_result
        if result is None:
            return "skip_advisory"
        if (
            result.recommend_advisory
            and self._settings.advisory_enabled
            and self._advisory_crew is not None
            and self._budget_state.degrade_level != "budget_stop"  # BudgetDegradeLevel.BUDGET_STOP
        ):
            return "advisory"
        return "skip_advisory"

    @listen("advisory")
    async def advisory_phase(self) -> None:
        """Run the advisory crew and apply directives to signals."""
        context_text = self._build_advisory_context()

        try:
            advisory_result = await self._advisory_crew.run(  # type: ignore[union-attr]
                context_text=context_text,
                uncertainty_score=self.state.uncertainty_score,
                verbose=self._settings.crewai_verbose,
            )
        except Exception:
            logger.exception("Advisory crew failed; proceeding with original signals")
            return

        self.state.advisory_ran = True
        self.state.advisory_adjustments = [adj.model_dump() for adj in advisory_result.adjustments]

        if not advisory_result.adjustments:
            logger.info("Advisory crew approved proposal without changes")
            return

        adjusted_signals = apply_advisory_directives(self.state.signals, advisory_result)
        logger.info(
            "Advisory applied %d adjustments: %d signals → %d signals",
            len(advisory_result.adjustments),
            len(self.state.signals),
            len(adjusted_signals),
        )

        self.state.signals = adjusted_signals
        self.state.risk_results.clear()
        self.state.order_requests.clear()

        held_symbols = list(self._portfolio.positions.keys())
        break_even_prices: dict[str, float | None] = (
            self._db.get_break_even_prices(held_symbols) if held_symbols else {}
        )
        for sig in adjusted_signals:
            analysis = self.state.market_analyses.get(sig.symbol)
            result = self._risk_pipeline.evaluate(sig, self._portfolio, analysis, break_even_prices)
            self.state.risk_results.append(result)
            order_req = self._risk_pipeline.to_order_request(sig, result)
            if order_req is not None:
                self.state.order_requests.append(order_req)
            self._db.save_signal(sig, risk_verdict=result.verdict.value)

        logger.info(
            "Post-advisory re-derivation: %d order requests",
            len(self.state.order_requests),
        )

    @listen(or_("skip_advisory", advisory_phase))
    async def reserve_phase(self) -> None:
        """Apply tentative portfolio reservations from final order requests."""
        self._portfolio_snapshot = self._portfolio.model_copy(deep=True)
        for req in self.state.order_requests:
            _apply_single_order_to_portfolio(self._portfolio, req)

        if self.state.order_requests:
            self._portfolio.update_peak()
            logger.info(
                "Portfolio (tentative): balance=%.2f, positions=%d, exposure=%.1f%%",
                self._portfolio.balance_quote,
                len(self._portfolio.positions),
                self._portfolio.exposure_pct,
            )

    @router(reserve_phase)
    async def route_after_reserve(self) -> str:
        if not self._plan.run_execution:
            return "skip_execution"
        return "execution"

    @listen("execution_only")
    async def execution_only_phase(self) -> None:
        """Poll and reconcile open orders when strategy was skipped."""
        logger.info("Running execution-only pipeline (strategy skipped, open orders exist)...")
        try:
            poll_result = await self._execution_service.poll_and_reconcile(self._portfolio)
            self.state.orders = poll_result.placed
            self.state.filled_orders = poll_result.filled
            self.state.cancelled_orders = poll_result.cancelled
            self.state.failed_orders = [f.as_dict() for f in poll_result.failed]

            logger.info(
                "Execution-only pipeline: filled=%d, cancelled=%d, failed=%d",
                len(self.state.filled_orders),
                len(self.state.cancelled_orders),
                len(self.state.failed_orders),
            )
        except Exception:
            logger.exception("Execution-only pipeline failed")

    @listen("execution")
    async def execution_phase(self) -> None:
        """Place new orders and poll existing ones."""
        logger.info("Running execution pipeline...")
        try:
            exec_result = await self._execution_service.process_order_requests(
                self.state.order_requests, self._portfolio
            )
            poll_result = await self._execution_service.poll_and_reconcile(self._portfolio)

            self.state.orders = exec_result.placed + poll_result.placed
            self.state.filled_orders = exec_result.filled + poll_result.filled
            self.state.cancelled_orders = exec_result.cancelled + poll_result.cancelled
            self.state.failed_orders = [
                f.as_dict() for f in exec_result.failed + poll_result.failed
            ]

            logger.info(
                "Execution pipeline: placed=%d, filled=%d, cancelled=%d, failed=%d",
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

            self._portfolio_snapshot = None

        except Exception:
            logger.exception("Execution pipeline failed")
            _rollback_portfolio(self._portfolio, self._portfolio_snapshot, self.state)
            self._portfolio_snapshot = None
            self._notif.notify_error("Execution pipeline failed — reservations rolled back")

    @router(execution_phase)
    async def route_after_execution(self) -> str:
        return "post_cycle"

    @listen(or_("skip_strategy", "skip_execution", "post_cycle", execution_only_phase))
    async def post_cycle_hooks(self) -> None:
        """Run post-cycle finalisation: rollback, hooks, stop-loss, persistence."""
        if self._portfolio_snapshot is not None:
            open_orders_label = (
                str(self._plan.open_orders_count)
                if self._plan.open_orders_count is not None
                else "n/a"
            )
            logger.info(
                "Skipping execution (interval not due or no open orders: %s)",
                open_orders_label,
            )
            _rollback_portfolio(self._portfolio, self._portfolio_snapshot, self.state)
            self._portfolio_snapshot = None

        for order in self.state.filled_orders:
            self._on_order_filled(order)

        if self._settings.stop_loss_monitoring_enabled:
            await self._check_stop_losses()

        if self._settings.save_cycle_history:
            try:
                self._db.save_cycle_summary(self.state, self._portfolio)
            except Exception:
                logger.exception(
                    "Failed to persist cycle summary for cycle %d",
                    self.state.cycle_number,
                )

        try:
            self._db.save_portfolio(self._portfolio)
        except Exception:
            logger.exception("Failed to save portfolio snapshot")

        logger.info(self.state.summary)

    @listen("halt")
    async def circuit_breaker_halt(self) -> None:
        """Terminal handler when the circuit breaker is tripped."""
        self.state.circuit_breaker_tripped = True
        self._on_circuit_breaker_activated()

    # -------------------------------------------------------------------------
    # Event hooks
    # -------------------------------------------------------------------------

    def _on_order_filled(self, order: Order) -> None:
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
        self._circuit_breaker.check(self._portfolio)

    def _on_circuit_breaker_activated(self) -> None:
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
            price=current_price,
            strategy_name=pos.strategy_name or "stop_loss",
        )
        snapshot = self._portfolio.model_copy(deep=True)
        _apply_single_order_to_portfolio(self._portfolio, req)
        try:
            sl_result = await self._execution_service.process_order_requests([req], self._portfolio)
            self.state.orders = list(self.state.orders) + sl_result.placed
            self.state.filled_orders = list(self.state.filled_orders) + sl_result.filled
            self.state.failed_orders = list(self.state.failed_orders) + [
                f.as_dict() for f in sl_result.failed
            ]
        except Exception:
            logger.exception(
                "Stop-loss order placement failed for %s — rolling back portfolio", symbol
            )
            self._portfolio.balance_quote = snapshot.balance_quote
            self._portfolio.positions = snapshot.positions
            self._portfolio.peak_balance = snapshot.peak_balance
        self._notif.notify_error(
            f"Stop-loss triggered for {symbol} @ {current_price:.4f} "
            f"(stop={pos.stop_loss_price:.4f}). SELL order submitted."
        )

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    async def _check_stop_losses(self) -> None:
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
        for symbol, pos in self._portfolio.positions.items():
            analysis = self.state.market_analyses.get(symbol)
            if analysis is not None:
                self._portfolio.positions[symbol] = pos.model_copy(
                    update={"current_price": analysis.current_price}
                )

    def _build_advisory_context(self) -> str:
        """Format pipeline output as text for the advisory crew."""
        parts: list[str] = []

        parts.append("== Market Analyses ==")
        for symbol, analysis in self.state.market_analyses.items():
            parts.append(
                f"  {symbol}: price={analysis.current_price:.2f}, "
                f"regime={analysis.metadata.market_regime}, "
                f"indicators={json.dumps({k: round(v, 4) for k, v in analysis.indicators.items()})}"
            )

        parts.append("\n== Signals ==")
        for sig in self.state.signals:
            parts.append(
                f"  {sig.signal_type.value} {sig.symbol}: confidence={sig.confidence:.2f}, "
                f"strategy={sig.strategy_name}, reason={sig.reason}"
            )

        parts.append("\n== Risk Results ==")
        for sig, rr in zip(self.state.signals, self.state.risk_results, strict=False):
            parts.append(
                f"  {sig.symbol}: verdict={rr.verdict.value}, amount={rr.approved_amount:.6f}"
            )

        parts.append("\n== Portfolio ==")
        parts.append(
            f"  balance={self._portfolio.balance_quote:.2f}, "
            f"positions={len(self._portfolio.positions)}, "
            f"drawdown={self._portfolio.drawdown_pct:.2f}%, "
            f"exposure={self._portfolio.exposure_pct:.1f}%"
        )

        parts.append(f"\n== Uncertainty Score: {self.state.uncertainty_score:.3f} ==")
        parts.append(f"  Factors: {', '.join(self.state.uncertainty_factors)}")

        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _apply_market_data_gate(plan: RunPlan, state: CycleState) -> RunPlan:
    from trading_crew.main import _apply_market_data_gate as _gate

    return _gate(plan, state)


def _apply_single_order_to_portfolio(portfolio: Portfolio, req: OrderRequest) -> None:
    from trading_crew.main import _apply_single_order_to_portfolio as _apply

    _apply(portfolio, req)


def _rollback_portfolio(
    portfolio: Portfolio, snapshot: Portfolio | None, state: CycleState
) -> None:
    from trading_crew.main import _rollback_portfolio as _rollback

    _rollback(portfolio, snapshot, state)
