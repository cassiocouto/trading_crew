"""Unit tests for cost-contention scheduling and budget policy helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from trading_crew.config.settings import Settings, TokenBudgetDegradeMode
from trading_crew.main import (
    BudgetDegradeLevel,
    BudgetRuntimeState,
    RunPlan,
    _accumulate_estimated_tokens,
    _apply_degrade_to_plan,
    _apply_market_data_gate,
    _build_run_plan,
    _is_due,
    _refresh_budget_day,
    _update_degrade_level,
)
from trading_crew.models.cycle import CycleState
from trading_crew.services.notification_service import NotificationService


class _DbCountStub:
    def __init__(self, count: int) -> None:
        self._count = count

    def count_open_orders(self) -> int:
        return self._count


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "cost_contention_enabled": True,
        "market_crew_interval_seconds": 900,
        "strategy_crew_interval_seconds": 900,
        "execution_crew_interval_seconds": 900,
        "daily_token_budget_enabled": True,
        "daily_token_budget_tokens": 600_000,
        "token_budget_degrade_mode": TokenBudgetDegradeMode.STRATEGY_ONLY,
        "market_crew_estimated_tokens": 1_500,
        "strategy_crew_estimated_tokens": 6_000,
        "execution_crew_estimated_tokens": 1_000,
    }
    base.update(overrides)
    return Settings(**base)


@pytest.mark.unit
def test_is_due() -> None:
    assert _is_due(100.0, None, 30) is True
    assert _is_due(100.0, 80.0, 30) is False
    assert _is_due(100.0, 70.0, 30) is True


@pytest.mark.unit
def test_build_run_plan_disabled_contention_runs_everything() -> None:
    settings = _settings(cost_contention_enabled=False)
    plan = _build_run_plan(
        settings,
        _DbCountStub(3),
        now=1000.0,
        last_market_run=900.0,
        last_strategy_run=900.0,
        last_execution_run=900.0,
    )
    assert plan.run_market is True
    assert plan.run_strategy is True
    assert plan.run_execution is True
    assert plan.open_orders_count is None


@pytest.mark.unit
def test_build_run_plan_strategy_not_coupled_to_market_schedule() -> None:
    settings = _settings()
    plan = _build_run_plan(
        settings,
        _DbCountStub(1),
        now=1000.0,
        last_market_run=500.0,   # market not due
        last_strategy_run=0.0,   # strategy due
        last_execution_run=0.0,  # execution due
    )
    assert plan.run_market is False
    assert plan.run_strategy is True
    assert plan.run_execution is True
    assert plan.open_orders_count == 1


@pytest.mark.unit
def test_refresh_budget_day_resets_state_on_rollover() -> None:
    settings = _settings()
    state = BudgetRuntimeState(
        token_budget_day=date(2000, 1, 1),
        estimated_tokens_used_today=12345,
        budget_breach_notified=True,
        degrade_level=BudgetDegradeLevel.HARD_STOP,
    )
    _refresh_budget_day(settings, state)
    assert state.token_budget_day == datetime.now(UTC).date()
    assert state.estimated_tokens_used_today == 0
    assert state.budget_breach_notified is False
    assert state.degrade_level == BudgetDegradeLevel.NORMAL


@pytest.mark.unit
def test_update_degrade_level_strategy_then_hard_stop() -> None:
    notifier = NotificationService(channels=[])
    state = BudgetRuntimeState(
        token_budget_day=datetime.now(UTC).date(),
        estimated_tokens_used_today=595_000,
    )
    strategy_only = _settings(token_budget_degrade_mode=TokenBudgetDegradeMode.STRATEGY_ONLY)
    _update_degrade_level(strategy_only, state, notifier)
    assert state.degrade_level == BudgetDegradeLevel.STRATEGY_OFF
    assert state.budget_breach_notified is True

    hard_stop = _settings(token_budget_degrade_mode=TokenBudgetDegradeMode.HARD_STOP)
    state.estimated_tokens_used_today = 600_000
    _update_degrade_level(hard_stop, state, notifier)
    assert state.degrade_level == BudgetDegradeLevel.HARD_STOP


@pytest.mark.unit
def test_apply_degrade_to_plan() -> None:
    settings = _settings()
    plan = RunPlan(run_market=True, run_strategy=True, run_execution=True, open_orders_count=2)
    state = BudgetRuntimeState(token_budget_day=datetime.now(UTC).date())
    state.degrade_level = BudgetDegradeLevel.STRATEGY_OFF
    out = _apply_degrade_to_plan(settings, state, plan)
    assert out.run_market is True
    assert out.run_strategy is False
    assert out.run_execution is True

    state.degrade_level = BudgetDegradeLevel.HARD_STOP
    out = _apply_degrade_to_plan(settings, state, plan)
    assert out.run_market is False
    assert out.run_strategy is False
    assert out.run_execution is False


@pytest.mark.unit
def test_accumulate_estimated_tokens() -> None:
    settings = _settings()
    state = BudgetRuntimeState(token_budget_day=datetime.now(UTC).date())
    _accumulate_estimated_tokens(settings, state, ran_market=True, ran_strategy=False, ran_execution=True)
    assert state.estimated_tokens_used_today == 2_500


@pytest.mark.unit
def test_apply_market_data_gate_disables_decision_crews_on_empty_analyses() -> None:
    plan = RunPlan(run_market=True, run_strategy=True, run_execution=True, open_orders_count=0)
    state = CycleState(cycle_number=1, symbols=["BTC/USDT"])
    out = _apply_market_data_gate(plan, state)
    assert out.run_strategy is False
    assert out.run_execution is False
