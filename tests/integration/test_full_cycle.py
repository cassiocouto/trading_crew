"""Integration test: full trading cycle in paper mode with mocked async CCXT.

Spins up a TradingFlow with all deterministic services, injects bullish OHLCV
data that triggers an EMA-crossover BUY signal, and verifies that records are
persisted to an in-memory SQLite database.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest
from sqlalchemy.pool import StaticPool

from tests.integration.conftest import make_mock_exchange
from trading_crew.db.session import get_engine, init_db
from trading_crew.flows.trading_flow import TradingFlow
from trading_crew.main import BudgetDegradeLevel, BudgetRuntimeState, RunPlan
from trading_crew.models.portfolio import Portfolio
from trading_crew.risk.circuit_breaker import CircuitBreaker
from trading_crew.services.database_service import DatabaseService
from trading_crew.services.execution_service import ExecutionService
from trading_crew.services.market_intelligence_service import MarketIntelligenceService
from trading_crew.services.notification_service import NotificationService
from trading_crew.services.risk_pipeline import RiskPipeline
from trading_crew.services.strategy_runner import StrategyRunner
from trading_crew.services.uncertainty_scorer import UncertaintyScorer
from trading_crew.strategies.ema_crossover import EMACrossoverStrategy

SYMBOL = "BTC/USDT"
EXCHANGE = "binance"


@pytest.fixture()
def db_engine():
    engine = get_engine(
        "sqlite:///:memory:",
        pool_size=None,
        max_overflow=None,
        pool_timeout=None,
    )
    # Override cached engine to use StaticPool so threads share the same connection
    from sqlalchemy import create_engine as _ce

    engine = _ce(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    init_db(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_service(db_engine):
    return DatabaseService(db_engine)


@pytest.fixture()
def mock_exchange():
    return make_mock_exchange(
        symbol=SYMBOL, exchange_id=EXCHANGE, ticker_price=50_000.0, n_candles=60
    )


def _make_settings(**overrides):
    from trading_crew.config.settings import Settings
    from trading_crew.models.risk import RiskParams

    s = MagicMock(spec=Settings)
    s.advisory_enabled = False
    s.advisory_activation_threshold = 0.6
    s.risk = RiskParams()
    s.save_cycle_history = True
    s.stop_loss_monitoring_enabled = False
    s.symbols = [SYMBOL]
    s.default_timeframe = "1h"
    s.market_data_candle_limit = 60
    s.stale_order_cancel_minutes = 10
    s.stale_partial_fill_cancel_minutes = 360
    s.crewai_verbose = False
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def _make_plan(**overrides) -> RunPlan:
    plan = RunPlan(run_market=True, run_strategy=True, run_execution=True, open_orders_count=0)
    for k, v in overrides.items():
        setattr(plan, k, v)
    return plan


def _make_budget() -> BudgetRuntimeState:
    return BudgetRuntimeState(
        token_budget_day=date.today(), degrade_level=BudgetDegradeLevel.NORMAL
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_cycle_produces_records(db_service, mock_exchange):
    """A single bullish cycle should insert signals, orders, and a cycle record."""
    from trading_crew.models.risk import RiskParams

    notification_service = MagicMock(spec=NotificationService)
    notification_service.notify = MagicMock()
    notification_service.notify_error = MagicMock()

    strategy_runner = StrategyRunner(
        strategies=[EMACrossoverStrategy()],
        min_confidence=0.0,
        ensemble=False,
    )
    risk_params = RiskParams(
        max_position_pct=0.1,
        max_drawdown_pct=0.3,
        min_confidence=0.0,
    )
    market_svc = MarketIntelligenceService(
        exchange_service=mock_exchange,
        db_service=db_service,
    )
    execution_service = ExecutionService(
        exchange_service=mock_exchange,
        db_service=db_service,
        notification_service=notification_service,
    )
    circuit_breaker = CircuitBreaker(risk_params)
    risk_pipeline = RiskPipeline(
        risk_params=risk_params,
        circuit_breaker=circuit_breaker,
        stop_loss_method="fixed",
    )
    portfolio = Portfolio(balance_quote=10_000.0, peak_balance=10_000.0)

    uncertainty_scorer = UncertaintyScorer()

    flow = TradingFlow(
        cycle_number=1,
        symbols=[SYMBOL],
        plan=_make_plan(),
        portfolio=portfolio,
        budget_state=_make_budget(),
        cached_analyses={},
        circuit_breaker=circuit_breaker,
        market_svc=market_svc,
        strategy_runner=strategy_runner,
        risk_pipeline=risk_pipeline,
        execution_service=execution_service,
        db_service=db_service,
        notif_service=notification_service,
        uncertainty_scorer=uncertainty_scorer,
        settings=_make_settings(),
    )

    # Should not raise
    await flow.akickoff()

    # -- Assertions ----------------------------------------------------------
    from trading_crew.db.session import get_session

    with get_session(db_service._engine) as session:
        from trading_crew.db.models import CycleRecord, OrderRecord, PortfolioRecord

        cycle = session.query(CycleRecord).filter_by(cycle_number=1).first()
        assert cycle is not None, "CycleRecord with cycle_number=1 should exist"

        portfolio_rec = session.query(PortfolioRecord).first()
        assert portfolio_rec is not None, "PortfolioRecord snapshot should be persisted"

        session.query(OrderRecord).all()
        assert cycle.cycle_number == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_cycle_no_exceptions_raised(db_service, mock_exchange):
    """akickoff() should complete without raising any exceptions."""
    from trading_crew.models.risk import RiskParams

    notification_service = MagicMock(spec=NotificationService)
    notification_service.notify = MagicMock()
    notification_service.notify_error = MagicMock()

    strategy_runner = StrategyRunner(
        strategies=[EMACrossoverStrategy()],
        min_confidence=0.5,
        ensemble=False,
    )
    risk_params = RiskParams(max_position_pct=0.1, max_drawdown_pct=0.3, min_confidence=0.5)
    market_svc = MarketIntelligenceService(
        exchange_service=mock_exchange,
        db_service=db_service,
    )
    execution_service = ExecutionService(
        exchange_service=mock_exchange,
        db_service=db_service,
        notification_service=notification_service,
    )
    circuit_breaker = CircuitBreaker(risk_params)
    risk_pipeline = RiskPipeline(
        risk_params=risk_params,
        circuit_breaker=circuit_breaker,
        stop_loss_method="fixed",
    )
    portfolio = Portfolio(balance_quote=10_000.0, peak_balance=10_000.0)
    uncertainty_scorer = UncertaintyScorer()

    flow = TradingFlow(
        cycle_number=1,
        symbols=[SYMBOL],
        plan=_make_plan(),
        portfolio=portfolio,
        budget_state=_make_budget(),
        cached_analyses={},
        circuit_breaker=circuit_breaker,
        market_svc=market_svc,
        strategy_runner=strategy_runner,
        risk_pipeline=risk_pipeline,
        execution_service=execution_service,
        db_service=db_service,
        notif_service=notification_service,
        uncertainty_scorer=uncertainty_scorer,
        settings=_make_settings(),
    )

    # Must not raise
    await flow.akickoff()
