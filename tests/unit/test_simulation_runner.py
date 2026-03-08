"""Tests for SimulationRunner.

These tests verify the runner's orchestration logic using real
``SimulatedExchangeService`` and in-memory SQLite, but patching out the
``TradingFlow`` to avoid needing live LLM keys.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from trading_crew.models.backtest import BacktestConfig, BacktestResult, EquityPoint
from trading_crew.models.market import OHLCV
from trading_crew.services.simulation_runner import SimulationRunner, _compute_metrics

TRADING_FLOW_PATH = "trading_crew.flows.trading_flow.TradingFlow"

pytestmark = pytest.mark.unit


def _make_candles(n: int = 100, base_price: float = 100.0) -> list[OHLCV]:
    return [
        OHLCV(
            symbol="BTC/USDT",
            exchange="binance",
            timeframe="1h",
            timestamp=datetime(2024, 1, 1, i % 24, tzinfo=UTC)
            if i < 24
            else datetime(2024, 1, 1 + i // 24, i % 24, tzinfo=UTC),
            open=base_price + i * 0.1,
            high=base_price + i * 0.1 + 2.0,
            low=base_price + i * 0.1 - 1.0,
            close=base_price + i * 0.1 + 1.0,
            volume=500.0,
        )
        for i in range(n)
    ]


def _make_settings() -> MagicMock:
    """Create a minimal mock Settings object."""
    s = MagicMock()
    s.risk.min_confidence = 0.5
    s.risk.max_position_size_pct = 0.2
    s.risk.max_portfolio_exposure_pct = 0.8
    s.risk.max_drawdown_pct = 0.1
    s.risk.default_stop_loss_pct = 0.03
    s.risk.risk_per_trade_pct = 0.02
    s.risk.cooldown_after_loss_seconds = 0
    s.ensemble_enabled = False
    s.ensemble_agreement_threshold = 0.5
    s.stop_loss_method.value = "fixed"
    s.atr_stop_multiplier = 2.0
    s.anti_averaging_down = False
    s.advisory_activation_threshold = 0.6
    s.market_data_candle_limit = 120
    s.crewai_verbose = False
    s.advisory_enabled = False
    s.save_cycle_history = True
    s.stop_loss_monitoring_enabled = True
    s.symbols = ["BTC/USDT"]
    s.model_copy = MagicMock(return_value=s)
    return s


def _make_strategy() -> MagicMock:
    strategy = MagicMock()
    strategy.name = "test_strategy"
    strategy.generate_signal = MagicMock(return_value=None)
    return strategy


class TestComputeMetrics:
    def test_basic_metrics(self) -> None:
        from trading_crew.models.backtest import BacktestTrade

        trades = [
            BacktestTrade(
                symbol="BTC/USDT",
                side="buy",
                strategy_name="test",
                entry_bar=0,
                exit_bar=10,
                entry_price=100,
                exit_price=110,
                amount=1.0,
                pnl=9.8,
                fee=0.2,
                exit_reason="sell_signal",
                opened_at=datetime(2024, 1, 1, tzinfo=UTC),
                closed_at=datetime(2024, 1, 1, 10, tzinfo=UTC),
            ),
            BacktestTrade(
                symbol="BTC/USDT",
                side="buy",
                strategy_name="test",
                entry_bar=15,
                exit_bar=20,
                entry_price=105,
                exit_price=103,
                amount=1.0,
                pnl=-2.2,
                fee=0.2,
                exit_reason="sell_signal",
                opened_at=datetime(2024, 1, 1, 15, tzinfo=UTC),
                closed_at=datetime(2024, 1, 1, 20, tzinfo=UTC),
            ),
        ]
        equity = [
            EquityPoint(
                timestamp=datetime(2024, 1, 1, i, tzinfo=UTC),
                balance=10000 + i * 10,
                unrealized_pnl=0,
                drawdown_pct=0,
            )
            for i in range(24)
        ]
        result = _compute_metrics(trades, equity, 10000.0, "1h")
        assert result["winning_trades"] == 1
        assert result["losing_trades"] == 1
        assert result["win_rate_pct"] == 50.0
        assert result["total_fees"] == pytest.approx(0.4)
        assert result["total_return_pct"] > 0

    def test_empty_trades(self) -> None:
        equity = [
            EquityPoint(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                balance=10000,
                unrealized_pnl=0,
                drawdown_pct=0,
            )
        ]
        result = _compute_metrics([], equity, 10000.0)
        assert result["winning_trades"] == 0
        assert result["losing_trades"] == 0
        assert result["win_rate_pct"] == 0.0

    def test_no_equity_points(self) -> None:
        result = _compute_metrics([], [], 10000.0)
        assert result["final_balance"] == 10000.0


class TestBuildTradesFIFO:
    """Tests for FIFO lot matching in _build_trades."""

    def _setup_db_with_orders(self, orders_data: list[dict]) -> tuple:
        """Create an in-memory DB and insert order records."""
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool

        from trading_crew.db.models import OrderRecord
        from trading_crew.db.session import get_session, init_db
        from trading_crew.services.database_service import DatabaseService

        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        init_db(engine)
        db_service = DatabaseService(engine)

        with get_session(engine) as session:
            for data in orders_data:
                record = OrderRecord(**data)
                session.add(record)
            session.commit()

        return db_service

    def test_multiple_buys_one_sell_pairs_fifo(self) -> None:
        """Two buys for the same symbol, one sell: FIFO matches the first buy."""
        candles = _make_candles(50)
        orders = [
            {
                "exchange_order_id": "buy-1",
                "symbol": "BTC/USDT",
                "exchange": "binance",
                "side": "buy",
                "order_type": "market",
                "status": "filled",
                "requested_amount": 0.5,
                "filled_amount": 0.5,
                "average_fill_price": 100.0,
                "total_fee": 0.05,
                "strategy_name": "strat_a",
                "created_at": datetime(2024, 1, 1, 0, tzinfo=UTC),
            },
            {
                "exchange_order_id": "buy-2",
                "symbol": "BTC/USDT",
                "exchange": "binance",
                "side": "buy",
                "order_type": "market",
                "status": "filled",
                "requested_amount": 0.3,
                "filled_amount": 0.3,
                "average_fill_price": 110.0,
                "total_fee": 0.033,
                "strategy_name": "strat_a",
                "created_at": datetime(2024, 1, 1, 2, tzinfo=UTC),
            },
            {
                "exchange_order_id": "sell-1",
                "symbol": "BTC/USDT",
                "exchange": "binance",
                "side": "sell",
                "order_type": "market",
                "status": "filled",
                "requested_amount": 0.5,
                "filled_amount": 0.5,
                "average_fill_price": 120.0,
                "total_fee": 0.06,
                "strategy_name": "strat_a",
                "created_at": datetime(2024, 1, 1, 5, tzinfo=UTC),
            },
        ]
        db_service = self._setup_db_with_orders(orders)
        settings = _make_settings()
        runner = SimulationRunner(strategies=[_make_strategy()], settings=settings)

        trades = runner._build_trades(db_service, "BTC/USDT", candles)

        assert len(trades) == 1
        assert trades[0].entry_price == 100.0  # FIFO: first buy
        assert trades[0].exit_price == 120.0
        assert trades[0].amount == 0.5

    def test_partial_fill_creates_residual(self) -> None:
        """Buy 1.0, sell 0.6 => trade for 0.6, residual 0.4 remains in queue."""
        candles = _make_candles(50)
        orders = [
            {
                "exchange_order_id": "buy-1",
                "symbol": "BTC/USDT",
                "exchange": "binance",
                "side": "buy",
                "order_type": "market",
                "status": "filled",
                "requested_amount": 1.0,
                "filled_amount": 1.0,
                "average_fill_price": 100.0,
                "total_fee": 0.1,
                "strategy_name": "strat_a",
                "created_at": datetime(2024, 1, 1, 0, tzinfo=UTC),
            },
            {
                "exchange_order_id": "sell-1",
                "symbol": "BTC/USDT",
                "exchange": "binance",
                "side": "sell",
                "order_type": "market",
                "status": "filled",
                "requested_amount": 0.6,
                "filled_amount": 0.6,
                "average_fill_price": 120.0,
                "total_fee": 0.072,
                "strategy_name": "strat_a",
                "created_at": datetime(2024, 1, 1, 5, tzinfo=UTC),
            },
            {
                "exchange_order_id": "sell-2",
                "symbol": "BTC/USDT",
                "exchange": "binance",
                "side": "sell",
                "order_type": "market",
                "status": "filled",
                "requested_amount": 0.4,
                "filled_amount": 0.4,
                "average_fill_price": 115.0,
                "total_fee": 0.046,
                "strategy_name": "strat_a",
                "created_at": datetime(2024, 1, 1, 10, tzinfo=UTC),
            },
        ]
        db_service = self._setup_db_with_orders(orders)
        settings = _make_settings()
        runner = SimulationRunner(strategies=[_make_strategy()], settings=settings)

        trades = runner._build_trades(db_service, "BTC/USDT", candles)

        assert len(trades) == 2
        assert trades[0].amount == pytest.approx(0.6)
        assert trades[0].entry_price == 100.0
        assert trades[0].exit_price == 120.0
        assert trades[1].amount == pytest.approx(0.4)
        assert trades[1].entry_price == 100.0
        assert trades[1].exit_price == 115.0

    def test_sell_spans_multiple_buys(self) -> None:
        """One large sell consumes multiple buy lots."""
        candles = _make_candles(50)
        orders = [
            {
                "exchange_order_id": "buy-1",
                "symbol": "BTC/USDT",
                "exchange": "binance",
                "side": "buy",
                "order_type": "market",
                "status": "filled",
                "requested_amount": 0.3,
                "filled_amount": 0.3,
                "average_fill_price": 100.0,
                "total_fee": 0.03,
                "strategy_name": "strat_a",
                "created_at": datetime(2024, 1, 1, 0, tzinfo=UTC),
            },
            {
                "exchange_order_id": "buy-2",
                "symbol": "BTC/USDT",
                "exchange": "binance",
                "side": "buy",
                "order_type": "market",
                "status": "filled",
                "requested_amount": 0.5,
                "filled_amount": 0.5,
                "average_fill_price": 110.0,
                "total_fee": 0.055,
                "strategy_name": "strat_a",
                "created_at": datetime(2024, 1, 1, 2, tzinfo=UTC),
            },
            {
                "exchange_order_id": "sell-1",
                "symbol": "BTC/USDT",
                "exchange": "binance",
                "side": "sell",
                "order_type": "market",
                "status": "filled",
                "requested_amount": 0.8,
                "filled_amount": 0.8,
                "average_fill_price": 120.0,
                "total_fee": 0.096,
                "strategy_name": "strat_a",
                "created_at": datetime(2024, 1, 1, 5, tzinfo=UTC),
            },
        ]
        db_service = self._setup_db_with_orders(orders)
        settings = _make_settings()
        runner = SimulationRunner(strategies=[_make_strategy()], settings=settings)

        trades = runner._build_trades(db_service, "BTC/USDT", candles)

        assert len(trades) == 2
        # First trade: entire first lot (0.3 @ 100)
        assert trades[0].amount == pytest.approx(0.3)
        assert trades[0].entry_price == 100.0
        # Second trade: partial second lot (0.5 @ 110)
        assert trades[1].amount == pytest.approx(0.5)
        assert trades[1].entry_price == 110.0

    def test_no_buy_orders_produces_no_trades(self) -> None:
        """Sell without any preceding buys produces no trades."""
        candles = _make_candles(50)
        orders = [
            {
                "exchange_order_id": "sell-1",
                "symbol": "BTC/USDT",
                "exchange": "binance",
                "side": "sell",
                "order_type": "market",
                "status": "filled",
                "requested_amount": 0.5,
                "filled_amount": 0.5,
                "average_fill_price": 120.0,
                "total_fee": 0.06,
                "strategy_name": "strat_a",
                "created_at": datetime(2024, 1, 1, 5, tzinfo=UTC),
            },
        ]
        db_service = self._setup_db_with_orders(orders)
        settings = _make_settings()
        runner = SimulationRunner(strategies=[_make_strategy()], settings=settings)

        trades = runner._build_trades(db_service, "BTC/USDT", candles)

        assert len(trades) == 0


class TestSimulationRunnerInit:
    def test_too_few_candles_raises(self) -> None:
        settings = _make_settings()
        config = BacktestConfig(min_candles_for_analysis=50)
        runner = SimulationRunner(
            strategies=[_make_strategy()],
            settings=settings,
            config=config,
        )
        with pytest.raises(ValueError, match="Need at least"):
            import asyncio

            asyncio.run(runner.run("BTC/USDT", "binance", _make_candles(30), "1h"))


class TestSimulationRunnerRun:
    """Integration-ish tests that run the full loop with a mocked TradingFlow."""

    @pytest.mark.asyncio
    async def test_produces_valid_result(self) -> None:
        """The runner should produce a BacktestResult with all required fields."""
        candles = _make_candles(80)
        settings = _make_settings()
        config = BacktestConfig(min_candles_for_analysis=20, initial_balance=10000.0)
        runner = SimulationRunner(
            strategies=[_make_strategy()],
            settings=settings,
            config=config,
        )

        mock_flow_cls = MagicMock()
        mock_flow_instance = MagicMock()
        mock_flow_instance.akickoff = AsyncMock()
        mock_flow_instance.state = MagicMock()
        mock_flow_instance.state.market_analyses = {}
        mock_flow_instance.state.uncertainty_score = 0.3
        mock_flow_instance.state.advisory_ran = False
        mock_flow_cls.return_value = mock_flow_instance

        with patch(TRADING_FLOW_PATH, mock_flow_cls):
            result = await runner.run("BTC/USDT", "binance", candles, "1h")

        assert isinstance(result, BacktestResult)
        assert result.symbol == "BTC/USDT"
        assert result.exchange == "binance"
        assert result.initial_balance == 10000.0
        assert len(result.equity_curve) == 60  # 80 - 20
        assert len(result.uncertainty_scores) == 60

    @pytest.mark.asyncio
    async def test_circuit_breaker_halts_simulation(self) -> None:
        """If circuit breaker trips, simulation should stop early."""
        candles = _make_candles(80)
        settings = _make_settings()
        config = BacktestConfig(min_candles_for_analysis=20)
        runner = SimulationRunner(
            strategies=[_make_strategy()],
            settings=settings,
            config=config,
        )

        call_count = 0

        async def _mock_kickoff() -> None:
            nonlocal call_count, mock_flow_instance
            call_count += 1
            if call_count >= 5:
                # Trip the circuit breaker from inside the flow
                mock_flow_instance._circuit_breaker_ref.is_tripped = True

        mock_flow_cls = MagicMock()
        mock_flow_instance = MagicMock()
        mock_flow_instance.akickoff = _mock_kickoff
        mock_flow_instance.state = MagicMock()
        mock_flow_instance.state.market_analyses = {}
        mock_flow_instance.state.uncertainty_score = 0.3
        mock_flow_instance.state.advisory_ran = False
        mock_flow_instance._circuit_breaker_ref = MagicMock()

        # We'll use a side_effect on the TradingFlow constructor to capture the
        # actual circuit breaker and wire up the tripping logic.
        real_cb = None

        def _flow_factory(**kwargs: object) -> MagicMock:
            nonlocal real_cb
            real_cb = kwargs.get("circuit_breaker")
            mock_flow_instance._circuit_breaker_ref = real_cb
            return mock_flow_instance

        mock_flow_cls.side_effect = _flow_factory

        with patch(TRADING_FLOW_PATH, mock_flow_cls):
            result = await runner.run("BTC/USDT", "binance", candles, "1h")

        assert call_count == 5
        assert len(result.equity_curve) == 5

    @pytest.mark.asyncio
    async def test_equity_curve_timestamps_match_candles(self) -> None:
        candles = _make_candles(80)
        settings = _make_settings()
        config = BacktestConfig(min_candles_for_analysis=20)
        runner = SimulationRunner(
            strategies=[_make_strategy()],
            settings=settings,
            config=config,
        )

        mock_flow_cls = MagicMock()
        mock_flow_instance = MagicMock()
        mock_flow_instance.akickoff = AsyncMock()
        mock_flow_instance.state = MagicMock()
        mock_flow_instance.state.market_analyses = {}
        mock_flow_instance.state.uncertainty_score = 0.0
        mock_flow_instance.state.advisory_ran = False
        mock_flow_cls.return_value = mock_flow_instance

        with patch(TRADING_FLOW_PATH, mock_flow_cls):
            result = await runner.run("BTC/USDT", "binance", candles, "1h")

        assert result.equity_curve[0].timestamp == candles[20].timestamp
        assert result.equity_curve[-1].timestamp == candles[79].timestamp
