"""Unit tests for budget policy, scheduling, and balance sync helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from trading_crew.config.settings import Settings, TokenBudgetDegradeMode
from trading_crew.main import (
    BudgetDegradeLevel,
    BudgetRuntimeState,
    RunPlan,
    _accumulate_estimated_tokens,
    _apply_market_data_gate,
    _build_run_plan,
    _is_due,
    _refresh_budget_day,
    _sync_balance_if_due,
    _update_degrade_level,
)
from trading_crew.models.cycle import CycleState
from trading_crew.models.portfolio import Portfolio
from trading_crew.services.notification_service import NotificationService


class _DbCountStub:
    def __init__(self, count: int) -> None:
        self._count = count

    def count_open_orders(self) -> int:
        return self._count


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "execution_poll_interval_seconds": 900,
        "advisory_enabled": True,
        "advisory_activation_threshold": 0.6,
        "advisory_estimated_tokens": 4_000,
        "daily_token_budget_enabled": True,
        "daily_token_budget_tokens": 600_000,
        "token_budget_degrade_mode": TokenBudgetDegradeMode.BUDGET_STOP,
    }
    base.update(overrides)
    return Settings(**base)


# ---------------------------------------------------------------------------
# _is_due
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_is_due_first_run() -> None:
    assert _is_due(100.0, None, 30) is True


@pytest.mark.unit
def test_is_due_not_elapsed() -> None:
    assert _is_due(100.0, 80.0, 30) is False


@pytest.mark.unit
def test_is_due_elapsed() -> None:
    assert _is_due(100.0, 70.0, 30) is True


# ---------------------------------------------------------------------------
# _build_run_plan — market and strategy always run
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_run_plan_market_and_strategy_always_run() -> None:
    settings = _settings()
    plan = _build_run_plan(
        settings,
        _DbCountStub(0),
        now=1000.0,
        last_execution_poll=999.0,
    )
    assert plan.run_market is True
    assert plan.run_strategy is True


@pytest.mark.unit
def test_build_run_plan_execution_runs_when_poll_due() -> None:
    settings = _settings(execution_poll_interval_seconds=60)
    plan = _build_run_plan(
        settings,
        _DbCountStub(2),
        now=1000.0,
        last_execution_poll=900.0,
    )
    assert plan.run_execution is True
    assert plan.open_orders_count == 2


@pytest.mark.unit
def test_build_run_plan_execution_skipped_when_poll_not_due() -> None:
    settings = _settings(execution_poll_interval_seconds=900)
    plan = _build_run_plan(
        settings,
        _DbCountStub(5),
        now=1000.0,
        last_execution_poll=999.0,
    )
    assert plan.run_execution is False


@pytest.mark.unit
def test_build_run_plan_execution_runs_on_first_cycle() -> None:
    settings = _settings()
    plan = _build_run_plan(
        settings,
        _DbCountStub(1),
        now=1000.0,
        last_execution_poll=None,
    )
    assert plan.run_execution is True
    assert plan.open_orders_count == 1


# ---------------------------------------------------------------------------
# _refresh_budget_day
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_refresh_budget_day_resets_on_new_utc_day() -> None:
    settings = _settings()
    state = BudgetRuntimeState(
        token_budget_day=date(2000, 1, 1),
        estimated_tokens_used_today=50_000,
        budget_breach_notified=True,
        degrade_level=BudgetDegradeLevel.BUDGET_STOP,
    )
    _refresh_budget_day(settings, state)
    assert state.token_budget_day == datetime.now(UTC).date()
    assert state.estimated_tokens_used_today == 0
    assert state.budget_breach_notified is False
    assert state.degrade_level == BudgetDegradeLevel.NORMAL


@pytest.mark.unit
def test_refresh_budget_day_noop_when_same_day() -> None:
    settings = _settings()
    today = datetime.now(UTC).date()
    state = BudgetRuntimeState(
        token_budget_day=today,
        estimated_tokens_used_today=42_000,
        budget_breach_notified=True,
        degrade_level=BudgetDegradeLevel.BUDGET_STOP,
    )
    _refresh_budget_day(settings, state)
    assert state.estimated_tokens_used_today == 42_000
    assert state.budget_breach_notified is True
    assert state.degrade_level == BudgetDegradeLevel.BUDGET_STOP


@pytest.mark.unit
def test_refresh_budget_day_noop_when_budget_disabled() -> None:
    settings = _settings(daily_token_budget_enabled=False)
    state = BudgetRuntimeState(
        token_budget_day=date(2000, 1, 1),
        estimated_tokens_used_today=99_999,
    )
    _refresh_budget_day(settings, state)
    assert state.estimated_tokens_used_today == 99_999


# ---------------------------------------------------------------------------
# _update_degrade_level
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_update_degrade_level_moves_to_budget_stop() -> None:
    notifier = NotificationService(channels=[])
    state = BudgetRuntimeState(
        token_budget_day=datetime.now(UTC).date(),
        estimated_tokens_used_today=600_000,
    )
    settings = _settings(token_budget_degrade_mode=TokenBudgetDegradeMode.BUDGET_STOP)
    _update_degrade_level(settings, state, notifier)
    assert state.degrade_level == BudgetDegradeLevel.BUDGET_STOP
    assert state.budget_breach_notified is True


@pytest.mark.unit
def test_update_degrade_level_stays_normal_below_budget() -> None:
    notifier = NotificationService(channels=[])
    state = BudgetRuntimeState(
        token_budget_day=datetime.now(UTC).date(),
        estimated_tokens_used_today=100_000,
    )
    settings = _settings(token_budget_degrade_mode=TokenBudgetDegradeMode.BUDGET_STOP)
    _update_degrade_level(settings, state, notifier)
    assert state.degrade_level == BudgetDegradeLevel.NORMAL
    assert state.budget_breach_notified is False


@pytest.mark.unit
def test_update_degrade_level_noop_when_mode_normal() -> None:
    notifier = NotificationService(channels=[])
    state = BudgetRuntimeState(
        token_budget_day=datetime.now(UTC).date(),
        estimated_tokens_used_today=999_999,
    )
    settings = _settings(token_budget_degrade_mode=TokenBudgetDegradeMode.NORMAL)
    _update_degrade_level(settings, state, notifier)
    assert state.degrade_level == BudgetDegradeLevel.NORMAL


@pytest.mark.unit
def test_update_degrade_level_noop_when_budget_disabled() -> None:
    notifier = NotificationService(channels=[])
    state = BudgetRuntimeState(
        token_budget_day=datetime.now(UTC).date(),
        estimated_tokens_used_today=999_999,
    )
    settings = _settings(
        daily_token_budget_enabled=False,
        token_budget_degrade_mode=TokenBudgetDegradeMode.BUDGET_STOP,
    )
    _update_degrade_level(settings, state, notifier)
    assert state.degrade_level == BudgetDegradeLevel.NORMAL


# ---------------------------------------------------------------------------
# _accumulate_estimated_tokens
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_accumulate_estimated_tokens_when_advisory_ran() -> None:
    settings = _settings(advisory_estimated_tokens=4_000)
    state = BudgetRuntimeState(token_budget_day=datetime.now(UTC).date())
    _accumulate_estimated_tokens(settings, state, advisory_ran=True)
    assert state.estimated_tokens_used_today == 4_000


@pytest.mark.unit
def test_accumulate_estimated_tokens_skipped_when_advisory_did_not_run() -> None:
    settings = _settings(advisory_estimated_tokens=4_000)
    state = BudgetRuntimeState(token_budget_day=datetime.now(UTC).date())
    _accumulate_estimated_tokens(settings, state, advisory_ran=False)
    assert state.estimated_tokens_used_today == 0


@pytest.mark.unit
def test_accumulate_estimated_tokens_noop_when_budget_disabled() -> None:
    settings = _settings(daily_token_budget_enabled=False, advisory_estimated_tokens=4_000)
    state = BudgetRuntimeState(token_budget_day=datetime.now(UTC).date())
    _accumulate_estimated_tokens(settings, state, advisory_ran=True)
    assert state.estimated_tokens_used_today == 0


@pytest.mark.unit
def test_accumulate_estimated_tokens_increments_cumulatively() -> None:
    settings = _settings(advisory_estimated_tokens=4_000)
    state = BudgetRuntimeState(token_budget_day=datetime.now(UTC).date())
    _accumulate_estimated_tokens(settings, state, advisory_ran=True)
    _accumulate_estimated_tokens(settings, state, advisory_ran=True)
    _accumulate_estimated_tokens(settings, state, advisory_ran=False)
    assert state.estimated_tokens_used_today == 8_000


# ---------------------------------------------------------------------------
# _apply_market_data_gate
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_apply_market_data_gate_disables_decision_crews_on_empty_analyses() -> None:
    plan = RunPlan(run_market=True, run_strategy=True, run_execution=True, open_orders_count=0)
    state = CycleState(cycle_number=1, symbols=["BTC/USDT"])
    out = _apply_market_data_gate(plan, state)
    assert out.run_strategy is False
    assert out.run_execution is False


# ---------------------------------------------------------------------------
# _sync_balance_if_due tests
# ---------------------------------------------------------------------------


def _mock_exchange(balance: dict[str, float] | None = None) -> MagicMock:
    mock = MagicMock()
    mock.fetch_balance = AsyncMock(return_value=balance or {"USDT": 9_500.0})
    return mock


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sync_balance_skips_when_interval_not_due() -> None:
    exchange = _mock_exchange()
    portfolio = Portfolio(balance_quote=10_000.0, peak_balance=10_000.0)
    notifier = MagicMock(spec=NotificationService)
    last_sync = datetime.now(UTC)

    result = await _sync_balance_if_due(exchange, portfolio, "USDT", 300, 1.0, notifier, last_sync)
    exchange.fetch_balance.assert_not_called()
    assert portfolio.balance_quote == 10_000.0
    assert result == last_sync


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sync_balance_updates_when_drift_exceeds_threshold() -> None:
    exchange = _mock_exchange({"USDT": 9_500.0})
    portfolio = Portfolio(balance_quote=10_000.0, peak_balance=10_000.0)
    notifier = MagicMock(spec=NotificationService)
    last_sync = datetime.now(UTC) - timedelta(seconds=301)

    result = await _sync_balance_if_due(exchange, portfolio, "USDT", 300, 1.0, notifier, last_sync)
    assert portfolio.balance_quote == 9_500.0
    notifier.notify.assert_called_once()
    assert result > last_sync


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sync_balance_no_alert_when_drift_below_threshold() -> None:
    exchange = _mock_exchange({"USDT": 9_995.0})
    portfolio = Portfolio(balance_quote=10_000.0, peak_balance=10_000.0)
    notifier = MagicMock(spec=NotificationService)
    last_sync = datetime.now(UTC) - timedelta(seconds=301)

    await _sync_balance_if_due(exchange, portfolio, "USDT", 300, 1.0, notifier, last_sync)
    assert portfolio.balance_quote == 9_995.0
    notifier.notify.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sync_balance_handles_fetch_failure_gracefully() -> None:
    exchange = MagicMock()
    exchange.fetch_balance = AsyncMock(side_effect=RuntimeError("connection timeout"))
    portfolio = Portfolio(balance_quote=10_000.0, peak_balance=10_000.0)
    notifier = MagicMock(spec=NotificationService)
    last_sync = datetime.now(UTC) - timedelta(seconds=301)

    result = await _sync_balance_if_due(exchange, portfolio, "USDT", 300, 1.0, notifier, last_sync)
    assert portfolio.balance_quote == 10_000.0
    notifier.notify.assert_not_called()
    assert result > last_sync


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sync_balance_skips_when_currency_not_in_response() -> None:
    exchange = _mock_exchange({"BTC": 0.5})
    portfolio = Portfolio(balance_quote=10_000.0, peak_balance=10_000.0)
    notifier = MagicMock(spec=NotificationService)
    last_sync = datetime.now(UTC) - timedelta(seconds=301)

    await _sync_balance_if_due(exchange, portfolio, "USDT", 300, 1.0, notifier, last_sync)
    assert portfolio.balance_quote == 10_000.0
