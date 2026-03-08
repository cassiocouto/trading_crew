"""Unit tests for TradingFlow (advisory architecture).

Tests cover:
  - All routing paths (route_after_market, route_after_reserve, route_after_execution)
  - Budget degrade integration (BUDGET_STOP)
  - Market data gate
  - Portfolio rollback on skip/failure
  - Event hooks (_on_order_filled, _on_circuit_breaker_activated, _on_stop_loss_triggered)
  - Stop-loss monitoring (_check_stop_losses)
  - Cycle persistence (save_cycle_summary gating)
  - Position price updates (_update_position_prices)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from trading_crew.flows.trading_flow import TradingFlow
from trading_crew.main import BudgetDegradeLevel, BudgetRuntimeState, RunPlan
from trading_crew.models.market import MarketAnalysis
from trading_crew.models.order import Order, OrderRequest, OrderSide, OrderStatus, OrderType
from trading_crew.models.portfolio import PnLSnapshot, Portfolio, Position
from trading_crew.services.uncertainty_scorer import UncertaintyScorer

# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------


def _make_settings(**overrides):
    """Return a minimal Settings-like stub."""
    from trading_crew.config.settings import Settings

    s = MagicMock(spec=Settings)
    s.crewai_verbose = False
    s.symbols = ["BTC/USDT"]
    s.default_timeframe = "1h"
    s.market_data_candle_limit = 120
    s.market_regime_volatility_threshold = 0.03
    s.market_regime_trend_threshold = 0.01
    s.save_cycle_history = True
    s.stop_loss_monitoring_enabled = True
    s.advisory_enabled = True
    s.advisory_activation_threshold = 0.6
    s.advisory_estimated_tokens = 4000
    s.execution_poll_interval_seconds = 900
    s.risk = MagicMock()
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def _make_plan(**overrides) -> RunPlan:
    plan = RunPlan(
        run_market=True,
        run_strategy=True,
        run_execution=True,
        open_orders_count=0,
    )
    for k, v in overrides.items():
        setattr(plan, k, v)
    return plan


def _make_budget(
    degrade_level: BudgetDegradeLevel = BudgetDegradeLevel.NORMAL,
) -> BudgetRuntimeState:
    from datetime import date

    b = BudgetRuntimeState(token_budget_day=date.today())
    b.degrade_level = degrade_level
    return b


def _make_portfolio(balance: float = 10_000.0) -> Portfolio:
    return Portfolio(balance_quote=balance, peak_balance=balance)


def _make_position(
    symbol: str = "BTC/USDT",
    current_price: float = 50_000.0,
    stop_loss_price: float | None = None,
) -> Position:
    return Position(
        symbol=symbol,
        exchange="binance",
        entry_price=50_000.0,
        amount=0.01,
        current_price=current_price,
        stop_loss_price=stop_loss_price,
    )


def _make_analysis(symbol: str = "BTC/USDT", current_price: float = 50_000.0) -> MarketAnalysis:
    from datetime import UTC, datetime

    return MarketAnalysis(
        symbol=symbol,
        exchange="binance",
        timestamp=datetime.now(UTC),
        current_price=current_price,
    )


def _make_order(symbol: str = "BTC/USDT") -> Order:
    req = OrderRequest(
        symbol=symbol,
        exchange="binance",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        amount=0.01,
    )
    return Order(id="oid-1", request=req, status=OrderStatus.FILLED)


def _make_exec_svc_mock(**kwargs) -> MagicMock:
    """Create an execution service mock with AsyncMock for async methods."""
    mock = MagicMock(**kwargs)
    mock.process_order_requests = AsyncMock(
        return_value=MagicMock(placed=[], filled=[], cancelled=[], failed=[])
    )
    mock.poll_and_reconcile = AsyncMock(
        return_value=MagicMock(placed=[], filled=[], cancelled=[], failed=[])
    )
    return mock


def _build_flow(
    plan: RunPlan | None = None,
    portfolio: Portfolio | None = None,
    budget: BudgetRuntimeState | None = None,
    settings=None,
    cached_analyses: dict | None = None,
    **service_overrides,
) -> TradingFlow:
    """Construct a TradingFlow with sensible mocked dependencies."""
    # Ensure execution_service has async methods unless explicitly overridden
    if "execution_service" not in service_overrides:
        service_overrides["execution_service"] = _make_exec_svc_mock()

    flow = TradingFlow(
        cycle_number=1,
        symbols=["BTC/USDT"],
        plan=plan or _make_plan(),
        portfolio=portfolio or _make_portfolio(),
        budget_state=budget or _make_budget(),
        cached_analyses=cached_analyses or {},
        circuit_breaker=service_overrides.get("circuit_breaker", MagicMock(is_tripped=False)),
        market_svc=service_overrides.get("market_svc", MagicMock()),
        strategy_runner=service_overrides.get(
            "strategy_runner", MagicMock(evaluate=MagicMock(return_value=[]))
        ),
        risk_pipeline=service_overrides.get("risk_pipeline", MagicMock()),
        execution_service=service_overrides["execution_service"],
        db_service=service_overrides.get("db_service", MagicMock()),
        notif_service=service_overrides.get("notif_service", MagicMock()),
        uncertainty_scorer=service_overrides.get("uncertainty_scorer", UncertaintyScorer()),
        advisory_crew=service_overrides.get("advisory_crew"),
        settings=settings or _make_settings(),
    )
    return flow


# ---------------------------------------------------------------------------
# TestFlowRouting
# ---------------------------------------------------------------------------


class TestFlowRouting:
    @pytest.mark.asyncio
    async def test_route_after_market_returns_halt_when_cb_tripped(self):
        cb = MagicMock(is_tripped=True, trip_reason="drawdown exceeded")
        flow = _build_flow(circuit_breaker=cb)
        assert await flow.route_after_market() == "halt"

    @pytest.mark.asyncio
    async def test_route_after_market_returns_skip_strategy_when_not_due_and_no_execution(self):
        flow = _build_flow(plan=_make_plan(run_strategy=False, run_execution=False))
        assert await flow.route_after_market() == "skip_strategy"

    @pytest.mark.asyncio
    async def test_route_after_market_returns_execution_only_when_strategy_skipped_but_execution_due(
        self,
    ):
        flow = _build_flow(plan=_make_plan(run_strategy=False, run_execution=True))
        assert await flow.route_after_market() == "execution_only"

    @pytest.mark.asyncio
    async def test_route_after_market_returns_strategy_normally(self):
        flow = _build_flow(plan=_make_plan(run_strategy=True))
        assert await flow.route_after_market() == "strategy"

    @pytest.mark.asyncio
    async def test_route_after_reserve_returns_skip_execution_when_not_due(self):
        flow = _build_flow(plan=_make_plan(run_execution=False))
        assert await flow.route_after_reserve() == "skip_execution"

    @pytest.mark.asyncio
    async def test_route_after_reserve_returns_execution_normally(self):
        flow = _build_flow(plan=_make_plan(run_execution=True))
        assert await flow.route_after_reserve() == "execution"

    @pytest.mark.asyncio
    async def test_route_after_execution_always_returns_post_cycle(self):
        flow = _build_flow()
        assert await flow.route_after_execution() == "post_cycle"


# ---------------------------------------------------------------------------
# TestMarketDataGate
# ---------------------------------------------------------------------------


class TestMarketDataGate:
    def test_gate_disables_strategy_when_no_analyses(self):
        flow = _build_flow(plan=_make_plan(run_strategy=True, open_orders_count=0))
        # Simulate: market ran but produced no data
        flow.state.market_analyses = {}
        from trading_crew.flows.trading_flow import _apply_market_data_gate

        _apply_market_data_gate(flow._plan, flow.state)
        assert flow._plan.run_strategy is False
        assert flow._plan.run_execution is False

    def test_gate_disables_strategy_but_keeps_execution_when_open_orders(self):
        flow = _build_flow(plan=_make_plan(run_strategy=True, open_orders_count=2))
        flow.state.market_analyses = {}
        from trading_crew.flows.trading_flow import _apply_market_data_gate

        _apply_market_data_gate(flow._plan, flow.state)
        assert flow._plan.run_strategy is False
        assert flow._plan.run_execution is True  # open orders keep it alive

    def test_gate_leaves_plan_unchanged_when_analyses_present(self):
        flow = _build_flow(plan=_make_plan(run_strategy=True, run_execution=True))
        flow.state.market_analyses = {"BTC/USDT": _make_analysis()}
        from trading_crew.flows.trading_flow import _apply_market_data_gate

        _apply_market_data_gate(flow._plan, flow.state)
        assert flow._plan.run_strategy is True
        assert flow._plan.run_execution is True


# ---------------------------------------------------------------------------
# TestBudgetDegrade
# ---------------------------------------------------------------------------


class TestBudgetDegrade:
    @pytest.mark.asyncio
    async def test_budget_stop_no_poll_when_execution_skipped(self):
        exec_svc = _make_exec_svc_mock()
        portfolio = _make_portfolio()
        flow = _build_flow(
            plan=_make_plan(run_execution=False),
            portfolio=portfolio,
            budget=_make_budget(BudgetDegradeLevel.BUDGET_STOP),
            execution_service=exec_svc,
        )
        flow._portfolio_snapshot = portfolio.model_copy(deep=True)
        await flow.post_cycle_hooks()
        exec_svc.poll_and_reconcile.assert_not_called()

    @pytest.mark.asyncio
    async def test_normal_degrade_no_poll_when_execution_skipped(self):
        exec_svc = _make_exec_svc_mock()
        portfolio = _make_portfolio()
        flow = _build_flow(
            plan=_make_plan(run_execution=False),
            portfolio=portfolio,
            budget=_make_budget(BudgetDegradeLevel.NORMAL),
            execution_service=exec_svc,
        )
        flow._portfolio_snapshot = portfolio.model_copy(deep=True)
        await flow.post_cycle_hooks()
        exec_svc.poll_and_reconcile.assert_not_called()


# ---------------------------------------------------------------------------
# TestPortfolioRollback
# ---------------------------------------------------------------------------


class TestPortfolioRollback:
    @pytest.mark.asyncio
    async def test_rollback_restores_portfolio_when_snapshot_non_none(self):
        original_balance = 9_000.0
        portfolio = _make_portfolio(balance=8_000.0)  # after tentative reservation
        snapshot = _make_portfolio(balance=original_balance)
        flow = _build_flow(portfolio=portfolio, plan=_make_plan(run_execution=False))
        flow._portfolio_snapshot = snapshot
        flow.state.order_requests = [MagicMock()]  # non-empty triggers rollback
        await flow.post_cycle_hooks()
        assert flow._portfolio.balance_quote == original_balance

    @pytest.mark.asyncio
    async def test_no_rollback_when_snapshot_is_none(self):
        portfolio = _make_portfolio(balance=8_000.0)
        flow = _build_flow(portfolio=portfolio)
        flow._portfolio_snapshot = None
        await flow.post_cycle_hooks()
        assert flow._portfolio.balance_quote == 8_000.0

    @pytest.mark.asyncio
    async def test_snapshot_cleared_after_rollback(self):
        portfolio = _make_portfolio()
        snapshot = portfolio.model_copy(deep=True)
        flow = _build_flow(portfolio=portfolio, plan=_make_plan(run_execution=False))
        flow._portfolio_snapshot = snapshot
        await flow.post_cycle_hooks()
        assert flow._portfolio_snapshot is None


# ---------------------------------------------------------------------------
# TestEventHooks
# ---------------------------------------------------------------------------


class TestEventHooks:
    def test_on_order_filled_saves_pnl_snapshot(self):
        db = MagicMock()
        portfolio = _make_portfolio()
        flow = _build_flow(portfolio=portfolio, db_service=db)
        order = _make_order()
        flow._on_order_filled(order)
        db.save_pnl_snapshot.assert_called_once()
        snapshot_arg = db.save_pnl_snapshot.call_args[0][0]
        assert isinstance(snapshot_arg, PnLSnapshot)

    def test_on_order_filled_rechecks_circuit_breaker(self):
        cb = MagicMock(is_tripped=False)
        portfolio = _make_portfolio()
        flow = _build_flow(portfolio=portfolio, circuit_breaker=cb)
        flow._on_order_filled(_make_order())
        cb.check.assert_called_once_with(portfolio)

    def test_on_circuit_breaker_activated_saves_portfolio_and_notifies(self):
        db = MagicMock()
        notif = MagicMock()
        cb = MagicMock(is_tripped=True, trip_reason="drawdown 30%")
        portfolio = _make_portfolio()
        flow = _build_flow(
            portfolio=portfolio, db_service=db, notif_service=notif, circuit_breaker=cb
        )
        flow._on_circuit_breaker_activated()
        db.save_portfolio.assert_called_once_with(portfolio)
        notif.notify_error.assert_called_once()
        assert "drawdown 30%" in notif.notify_error.call_args[0][0]

    @pytest.mark.asyncio
    async def test_on_stop_loss_triggered_submits_sell_order(self):
        exec_svc = _make_exec_svc_mock()
        notif = MagicMock()
        portfolio = _make_portfolio()
        portfolio.positions["BTC/USDT"] = _make_position(
            current_price=45_000.0, stop_loss_price=46_000.0
        )
        flow = _build_flow(portfolio=portfolio, execution_service=exec_svc, notif_service=notif)
        pos = portfolio.positions["BTC/USDT"]
        await flow._on_stop_loss_triggered("BTC/USDT", pos, 45_000.0)
        exec_svc.process_order_requests.assert_called_once()
        args = exec_svc.process_order_requests.call_args[0]
        reqs, _port = args[0], args[1]
        assert len(reqs) == 1
        assert reqs[0].side == OrderSide.SELL
        notif.notify_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_post_cycle_hooks_fires_on_order_filled_for_each_fill(self):
        db = MagicMock()
        flow = _build_flow(db_service=db)
        flow.state.filled_orders = [_make_order("BTC/USDT"), _make_order("ETH/USDT")]
        await flow.post_cycle_hooks()
        assert db.save_pnl_snapshot.call_count == 2


# ---------------------------------------------------------------------------
# TestStopLossMonitoring
# ---------------------------------------------------------------------------


class TestStopLossMonitoring:
    @pytest.mark.asyncio
    async def test_stop_loss_fires_when_price_below_stop(self):
        portfolio = _make_portfolio()
        portfolio.positions["BTC/USDT"] = _make_position(
            current_price=44_000.0, stop_loss_price=45_000.0
        )
        exec_svc = _make_exec_svc_mock()
        flow = _build_flow(
            portfolio=portfolio,
            execution_service=exec_svc,
            settings=_make_settings(stop_loss_monitoring_enabled=True),
        )
        flow.state.market_analyses = {"BTC/USDT": _make_analysis(current_price=44_000.0)}
        await flow._check_stop_losses()
        exec_svc.process_order_requests.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_loss_does_not_fire_when_price_above_stop(self):
        portfolio = _make_portfolio()
        portfolio.positions["BTC/USDT"] = _make_position(
            current_price=51_000.0, stop_loss_price=45_000.0
        )
        exec_svc = _make_exec_svc_mock()
        flow = _build_flow(
            portfolio=portfolio,
            execution_service=exec_svc,
            settings=_make_settings(stop_loss_monitoring_enabled=True),
        )
        flow.state.market_analyses = {"BTC/USDT": _make_analysis(current_price=51_000.0)}
        await flow._check_stop_losses()
        exec_svc.process_order_requests.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_loss_skipped_when_no_stop_price_set(self):
        portfolio = _make_portfolio()
        portfolio.positions["BTC/USDT"] = _make_position(stop_loss_price=None)
        exec_svc = _make_exec_svc_mock()
        flow = _build_flow(portfolio=portfolio, execution_service=exec_svc)
        flow.state.market_analyses = {"BTC/USDT": _make_analysis(current_price=44_000.0)}
        await flow._check_stop_losses()
        exec_svc.process_order_requests.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_loss_uses_cached_analyses_when_market_skipped(self):
        portfolio = _make_portfolio()
        portfolio.positions["BTC/USDT"] = _make_position(
            current_price=44_000.0, stop_loss_price=45_000.0
        )
        exec_svc = _make_exec_svc_mock()
        cached = {"BTC/USDT": _make_analysis(current_price=44_000.0)}
        flow = _build_flow(
            portfolio=portfolio,
            execution_service=exec_svc,
            cached_analyses=cached,
        )
        # Market phase was skipped → state.market_analyses is empty
        flow.state.market_analyses = {}
        await flow._check_stop_losses()
        exec_svc.process_order_requests.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_loss_skipped_when_no_analysis_for_symbol(self):
        portfolio = _make_portfolio()
        portfolio.positions["BTC/USDT"] = _make_position(
            current_price=44_000.0, stop_loss_price=45_000.0
        )
        exec_svc = _make_exec_svc_mock()
        flow = _build_flow(portfolio=portfolio, execution_service=exec_svc)
        flow.state.market_analyses = {}  # no data, no cache
        await flow._check_stop_losses()
        exec_svc.process_order_requests.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_loss_monitoring_disabled_skips_check(self):
        portfolio = _make_portfolio()
        portfolio.positions["BTC/USDT"] = _make_position(
            current_price=44_000.0, stop_loss_price=45_000.0
        )
        exec_svc = _make_exec_svc_mock()
        flow = _build_flow(
            portfolio=portfolio,
            execution_service=exec_svc,
            settings=_make_settings(stop_loss_monitoring_enabled=False),
        )
        flow.state.market_analyses = {"BTC/USDT": _make_analysis(current_price=44_000.0)}
        await flow.post_cycle_hooks()
        exec_svc.process_order_requests.assert_not_called()


# ---------------------------------------------------------------------------
# TestDedupSellOrders
# ---------------------------------------------------------------------------


class TestDedupSellOrders:
    """Tests for the _dedup_sell_orders module-level helper."""

    def test_duplicate_sells_merged_to_largest(self):
        from trading_crew.flows.trading_flow import _dedup_sell_orders

        portfolio = _make_portfolio()
        portfolio.positions["BTC/USDT"] = _make_position(current_price=50_000.0)

        req1 = OrderRequest(
            symbol="BTC/USDT",
            exchange="binance",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            amount=0.005,
            strategy_name="strat_a",
        )
        req2 = OrderRequest(
            symbol="BTC/USDT",
            exchange="binance",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            amount=0.01,
            strategy_name="strat_b",
        )
        req3 = OrderRequest(
            symbol="BTC/USDT",
            exchange="binance",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            amount=0.008,
            strategy_name="strat_c",
        )

        result = _dedup_sell_orders([req1, req2, req3], portfolio)
        sells = [r for r in result if r.side == OrderSide.SELL]
        assert len(sells) == 1
        assert sells[0].amount == 0.01  # largest

    def test_sell_capped_at_position_size(self):
        from trading_crew.flows.trading_flow import _dedup_sell_orders

        portfolio = _make_portfolio()
        portfolio.positions["BTC/USDT"] = _make_position(current_price=50_000.0)
        pos_amount = portfolio.positions["BTC/USDT"].amount  # 0.01

        # Request exceeds position
        req = OrderRequest(
            symbol="BTC/USDT",
            exchange="binance",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            amount=0.05,
            strategy_name="strat_x",
        )

        result = _dedup_sell_orders([req], portfolio)
        sells = [r for r in result if r.side == OrderSide.SELL]
        assert len(sells) == 1
        assert sells[0].amount == pos_amount

    def test_buy_orders_pass_through(self):
        from trading_crew.flows.trading_flow import _dedup_sell_orders

        portfolio = _make_portfolio()
        buy1 = OrderRequest(
            symbol="BTC/USDT",
            exchange="binance",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=0.01,
            strategy_name="strat_a",
        )
        buy2 = OrderRequest(
            symbol="ETH/USDT",
            exchange="binance",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=0.1,
            strategy_name="strat_b",
        )

        result = _dedup_sell_orders([buy1, buy2], portfolio)
        assert len(result) == 2

    def test_mixed_buy_and_sell(self):
        from trading_crew.flows.trading_flow import _dedup_sell_orders

        portfolio = _make_portfolio()
        portfolio.positions["BTC/USDT"] = _make_position(current_price=50_000.0)

        buy = OrderRequest(
            symbol="BTC/USDT",
            exchange="binance",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=0.01,
            strategy_name="strat_a",
        )
        sell1 = OrderRequest(
            symbol="BTC/USDT",
            exchange="binance",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            amount=0.005,
            strategy_name="strat_b",
        )
        sell2 = OrderRequest(
            symbol="BTC/USDT",
            exchange="binance",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            amount=0.01,
            strategy_name="strat_c",
        )

        result = _dedup_sell_orders([buy, sell1, sell2], portfolio)
        buys = [r for r in result if r.side == OrderSide.BUY]
        sells = [r for r in result if r.side == OrderSide.SELL]
        assert len(buys) == 1
        assert len(sells) == 1
        assert sells[0].amount == 0.01

    def test_empty_order_list(self):
        from trading_crew.flows.trading_flow import _dedup_sell_orders

        result = _dedup_sell_orders([], _make_portfolio())
        assert result == []


# ---------------------------------------------------------------------------
# TestStopLossNoTentativeReservation
# ---------------------------------------------------------------------------


class TestStopLossNoTentativeReservation:
    """Verify stop-loss handler doesn't tentatively mutate the portfolio."""

    @pytest.mark.asyncio
    async def test_stop_loss_preserves_position_before_execution(self):
        """Position should still exist in the portfolio when execution is called."""
        exec_svc = _make_exec_svc_mock()
        portfolio = _make_portfolio()
        portfolio.positions["BTC/USDT"] = _make_position(
            current_price=45_000.0, stop_loss_price=46_000.0
        )
        original_amount = portfolio.positions["BTC/USDT"].amount

        captured_portfolio = None

        async def _capture_portfolio(reqs, port, **kwargs):
            nonlocal captured_portfolio
            captured_portfolio = port
            return MagicMock(placed=[], filled=[], cancelled=[], failed=[])

        exec_svc.process_order_requests = _capture_portfolio

        flow = _build_flow(portfolio=portfolio, execution_service=exec_svc)
        pos = portfolio.positions["BTC/USDT"]
        await flow._on_stop_loss_triggered("BTC/USDT", pos, 45_000.0)

        # The portfolio passed to execution should still have the position
        assert "BTC/USDT" in captured_portfolio.positions
        assert captured_portfolio.positions["BTC/USDT"].amount == original_amount

    @pytest.mark.asyncio
    async def test_stop_loss_failure_preserves_position(self):
        """If execution fails, the position should remain unchanged."""
        exec_svc = _make_exec_svc_mock()
        exec_svc.process_order_requests = AsyncMock(side_effect=RuntimeError("exchange down"))

        portfolio = _make_portfolio()
        portfolio.positions["BTC/USDT"] = _make_position(
            current_price=45_000.0, stop_loss_price=46_000.0
        )
        original_amount = portfolio.positions["BTC/USDT"].amount

        flow = _build_flow(portfolio=portfolio, execution_service=exec_svc)
        pos = portfolio.positions["BTC/USDT"]
        await flow._on_stop_loss_triggered("BTC/USDT", pos, 45_000.0)

        assert "BTC/USDT" in portfolio.positions
        assert portfolio.positions["BTC/USDT"].amount == original_amount


# ---------------------------------------------------------------------------
# TestUpdatePositionPrices
# ---------------------------------------------------------------------------


class TestUpdatePositionPrices:
    def test_updates_current_price_from_analysis(self):
        portfolio = _make_portfolio()
        portfolio.positions["BTC/USDT"] = _make_position(current_price=50_000.0)
        flow = _build_flow(portfolio=portfolio)
        flow.state.market_analyses = {"BTC/USDT": _make_analysis(current_price=55_000.0)}
        flow._update_position_prices()
        assert portfolio.positions["BTC/USDT"].current_price == 55_000.0

    def test_leaves_price_unchanged_when_no_analysis_for_symbol(self):
        portfolio = _make_portfolio()
        portfolio.positions["BTC/USDT"] = _make_position(current_price=50_000.0)
        flow = _build_flow(portfolio=portfolio)
        flow.state.market_analyses = {}
        flow._update_position_prices()
        assert portfolio.positions["BTC/USDT"].current_price == 50_000.0


# ---------------------------------------------------------------------------
# TestCyclePersistence
# ---------------------------------------------------------------------------


class TestCyclePersistence:
    @pytest.mark.asyncio
    async def test_save_cycle_summary_called_when_enabled(self):
        db = MagicMock()
        portfolio = _make_portfolio()
        flow = _build_flow(
            portfolio=portfolio,
            db_service=db,
            settings=_make_settings(save_cycle_history=True),
        )
        await flow.post_cycle_hooks()
        db.save_cycle_summary.assert_called_once()
        # CrewAI's flow.state property creates a new wrapper on each access so
        # identity checks fail. Verify by cycle_number and portfolio identity.
        args = db.save_cycle_summary.call_args[0]
        assert args[0].cycle_number == 1
        assert args[1] is portfolio

    @pytest.mark.asyncio
    async def test_save_cycle_summary_skipped_when_disabled(self):
        db = MagicMock()
        flow = _build_flow(
            db_service=db,
            settings=_make_settings(save_cycle_history=False),
        )
        await flow.post_cycle_hooks()
        db.save_cycle_summary.assert_not_called()

    @pytest.mark.asyncio
    async def test_save_portfolio_always_called_in_post_cycle(self):
        db = MagicMock()
        portfolio = _make_portfolio()
        flow = _build_flow(portfolio=portfolio, db_service=db)
        await flow.post_cycle_hooks()
        db.save_portfolio.assert_called_once_with(portfolio)
