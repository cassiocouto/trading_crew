"""Trading Crew — main entry point.

Initializes all services and runs the trading loop.

CURRENT STATUS (v0.6.0 — Phase 6: Backtesting Engine):
  Each cycle is orchestrated by ``TradingFlow`` — a CrewAI Flow that wires
  the market, strategy, and execution phases with typed routing, event hooks
  (on_order_filled, on_circuit_breaker_activated, on_stop_loss_triggered),
  stop-loss monitoring, and per-cycle DB persistence.

  main() retains only the inter-cycle concerns that span the full run:
    - budget refresh and token accumulation
    - interval scheduling (RunPlan computation)
    - sleep between cycles
    - cross-cycle market-analysis cache (for stop-loss fallback)
    - graceful shutdown and final portfolio persistence

Usage:
    trading-crew              # via installed script
    python -m trading_crew.main
    make paper-trade
"""

from __future__ import annotations

import logging
import signal
import sys
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from trading_crew.models.cycle import CycleState

from trading_crew.agents.analyst import create_analyst_agent
from trading_crew.agents.executor import create_executor_agent
from trading_crew.agents.monitor import create_monitor_agent
from trading_crew.agents.risk_manager import create_risk_manager_agent
from trading_crew.agents.sentiment import create_sentiment_agent
from trading_crew.agents.sentinel import create_sentinel_agent
from trading_crew.agents.strategist import create_strategist_agent
from trading_crew.config.settings import (
    Settings,
    TokenBudgetDegradeMode,
    get_settings,
)
from trading_crew.crews.execution_crew import ExecutionCrew
from trading_crew.crews.market_crew import MarketCrew
from trading_crew.crews.strategy_crew import StrategyCrew
from trading_crew.db.session import get_engine, init_db
from trading_crew.flows.trading_flow import TradingFlow
from trading_crew.models.order import OrderRequest, OrderSide
from trading_crew.models.portfolio import Portfolio, Position
from trading_crew.risk.circuit_breaker import CircuitBreaker
from trading_crew.services.database_service import DatabaseService
from trading_crew.services.exchange_service import ExchangeService
from trading_crew.services.execution_service import ExecutionService
from trading_crew.services.market_intelligence_service import MarketIntelligenceService
from trading_crew.services.notification_service import NotificationService
from trading_crew.services.risk_pipeline import RiskPipeline
from trading_crew.services.sentiment_service import SentimentService
from trading_crew.services.strategy_runner import StrategyRunner
from trading_crew.strategies.bollinger import BollingerBandsStrategy
from trading_crew.strategies.ema_crossover import EMACrossoverStrategy
from trading_crew.strategies.rsi_range import RSIRangeStrategy

logger = logging.getLogger("trading_crew")

_shutdown_requested = False


class BudgetDegradeLevel(StrEnum):
    """Runtime degrade stage for daily token budget controls."""

    NORMAL = "normal"
    STRATEGY_OFF = "strategy_off"
    HARD_STOP = "hard_stop"


@dataclass
class RunPlan:
    """Planned crew execution for a cycle."""

    run_market: bool = True
    run_strategy: bool = True
    run_execution: bool = True
    open_orders_count: int | None = None


@dataclass
class BudgetRuntimeState:
    """Mutable runtime state for token budget and degrade tracking."""

    token_budget_day: date
    estimated_tokens_used_today: int = 0
    budget_breach_notified: bool = False
    degrade_level: BudgetDegradeLevel = BudgetDegradeLevel.NORMAL


def _setup_logging(level: str) -> None:
    """Configure structured logging for the application."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("trading_crew.log", encoding="utf-8"),
        ],
    )


def _handle_shutdown(signum: int, frame: object) -> None:
    """Handle graceful shutdown on SIGINT/SIGTERM."""
    global _shutdown_requested
    _shutdown_requested = True
    logger.info("Shutdown requested (signal %d). Finishing current cycle...", signum)


def _load_yaml(path: str) -> dict[str, dict[str, str]]:
    """Load a YAML configuration file."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _is_due(now: float, last_run: float | None, interval_seconds: int) -> bool:
    """Return True when a scheduled operation is due to run."""
    return last_run is None or (now - last_run) >= interval_seconds


def _utc_today() -> date:
    """Return the current UTC calendar date."""
    return datetime.now(UTC).date()




def _refresh_budget_day(settings: Settings, budget_state: BudgetRuntimeState) -> None:
    """Reset daily budget counters when UTC day changes."""
    if not settings.daily_token_budget_enabled:
        return

    today = _utc_today()
    if today != budget_state.token_budget_day:
        logger.info(
            "Resetting daily token budget counters: date=%s -> %s, used=%d",
            budget_state.token_budget_day,
            today,
            budget_state.estimated_tokens_used_today,
        )
        budget_state.token_budget_day = today
        budget_state.estimated_tokens_used_today = 0
        budget_state.budget_breach_notified = False
        budget_state.degrade_level = BudgetDegradeLevel.NORMAL


def _build_run_plan(
    settings: Settings,
    db_service: DatabaseService,
    now: float,
    last_market_run: float | None,
    last_strategy_run: float | None,
    last_execution_run: float | None,
) -> RunPlan:
    """Compute base crew run plan from interval scheduling rules."""
    plan = RunPlan()

    if not settings.cost_contention_enabled:
        return plan

    plan.run_market = _is_due(now, last_market_run, settings.market_crew_interval_seconds)
    plan.run_strategy = _is_due(now, last_strategy_run, settings.strategy_crew_interval_seconds)

    execution_due = _is_due(now, last_execution_run, settings.execution_crew_interval_seconds)
    if execution_due:
        plan.open_orders_count = db_service.count_open_orders()
        plan.run_execution = plan.run_strategy or plan.open_orders_count > 0
    else:
        plan.run_execution = False

    return plan


def _notify_budget_breach_once(
    budget_state: BudgetRuntimeState,
    notification_service: NotificationService,
    message: str,
) -> None:
    """Send budget-breach notification at most once per UTC day."""
    if budget_state.budget_breach_notified:
        return
    notification_service.notify(message)
    budget_state.budget_breach_notified = True


def _update_degrade_level(
    settings: Settings,
    budget_state: BudgetRuntimeState,
    notification_service: NotificationService,
) -> None:
    """Advance degrade level according to configured token-budget policy."""
    if not settings.daily_token_budget_enabled:
        return

    if (
        settings.token_budget_degrade_mode
        in (TokenBudgetDegradeMode.STRATEGY_ONLY, TokenBudgetDegradeMode.HARD_STOP)
        and budget_state.degrade_level == BudgetDegradeLevel.NORMAL
        and (
            budget_state.estimated_tokens_used_today + settings.strategy_crew_estimated_tokens
            > settings.daily_token_budget_tokens
        )
    ):
        budget_state.degrade_level = BudgetDegradeLevel.STRATEGY_OFF
        logger.warning(
            "Daily token budget guard activated: used=%d, budget=%d. "
            "Strategy crew disabled for the rest of the UTC day.",
            budget_state.estimated_tokens_used_today,
            settings.daily_token_budget_tokens,
        )
        _notify_budget_breach_once(
            budget_state,
            notification_service,
            "Daily token budget reached. Strategy crew disabled until UTC day reset.",
        )

    if (
        settings.token_budget_degrade_mode == TokenBudgetDegradeMode.HARD_STOP
        and budget_state.degrade_level != BudgetDegradeLevel.HARD_STOP
        and budget_state.estimated_tokens_used_today >= settings.daily_token_budget_tokens
    ):
        budget_state.degrade_level = BudgetDegradeLevel.HARD_STOP
        logger.warning(
            "Hard-stop mode activated: estimated daily token budget exhausted "
            "(used=%d, budget=%d). All LLM crews disabled until UTC reset.",
            budget_state.estimated_tokens_used_today,
            settings.daily_token_budget_tokens,
        )
        _notify_budget_breach_once(
            budget_state,
            notification_service,
            "Daily token budget exhausted. Hard-stop mode enabled until UTC day reset.",
        )


def _apply_degrade_to_plan(
    settings: Settings,
    budget_state: BudgetRuntimeState,
    plan: RunPlan,
) -> RunPlan:
    """Overlay budget degrade constraints onto run plan."""
    if budget_state.degrade_level in (
        BudgetDegradeLevel.STRATEGY_OFF,
        BudgetDegradeLevel.HARD_STOP,
    ):
        plan.run_strategy = False
        if settings.cost_contention_enabled:
            plan.run_execution = bool(plan.open_orders_count and plan.open_orders_count > 0)

    if budget_state.degrade_level == BudgetDegradeLevel.HARD_STOP:
        plan.run_market = False
        plan.run_strategy = False
        plan.run_execution = False

    return plan


def _accumulate_estimated_tokens(
    settings: Settings,
    budget_state: BudgetRuntimeState,
    ran_market: bool,
    ran_strategy: bool,
    ran_execution: bool,
) -> None:
    """Increment estimated token usage counters based on executed crews."""
    if not settings.daily_token_budget_enabled:
        return
    if ran_market:
        budget_state.estimated_tokens_used_today += settings.market_crew_estimated_tokens
    if ran_strategy:
        budget_state.estimated_tokens_used_today += settings.strategy_crew_estimated_tokens
    if ran_execution:
        budget_state.estimated_tokens_used_today += settings.execution_crew_estimated_tokens


def _apply_market_data_gate(plan: RunPlan, state: CycleState) -> RunPlan:
    """Skip downstream decision crews when no market analyses are available."""
    if state.market_analyses:
        return plan
    plan.run_strategy = False
    if plan.open_orders_count is None or plan.open_orders_count <= 0:
        plan.run_execution = False
    return plan


def _apply_single_order_to_portfolio(
    portfolio: Portfolio,
    req: OrderRequest,
) -> None:
    """Reserve capital for one approved order request.

    BUY: deduct notional from balance and add a proportionally-sized position.
    When balance is insufficient to cover the full notional, both the deduction
    and the booked amount are scaled down so market-value never exceeds the
    capital actually reserved.

    SELL: credit notional ONLY if a position exists to sell; capped at held
    amount to prevent phantom-cash creation (no short-selling model yet).

    These are tentative reservations — actual fill reconciliation will
    replace them in Phase 4 (Execution Crew).
    """
    price = req.price or 0.0
    notional = req.amount * price

    if req.side == OrderSide.BUY:
        affordable_notional = min(notional, portfolio.balance_quote)
        if affordable_notional <= 0:
            return
        portfolio.balance_quote -= affordable_notional

        buy_amount = affordable_notional / price if price > 0 else 0.0
        if buy_amount <= 0:
            return

        if req.symbol in portfolio.positions:
            pos = portfolio.positions[req.symbol]
            total_amount = pos.amount + buy_amount
            avg_price = (pos.entry_price * pos.amount + price * buy_amount) / total_amount
            portfolio.positions[req.symbol] = pos.model_copy(
                update={
                    "amount": total_amount,
                    "entry_price": avg_price,
                    "current_price": price or pos.current_price,
                }
            )
        else:
            portfolio.positions[req.symbol] = Position(
                symbol=req.symbol,
                exchange=req.exchange,
                entry_price=price,
                amount=buy_amount,
                current_price=price,
                stop_loss_price=req.stop_loss_price,
                take_profit_price=req.take_profit_price,
                strategy_name=req.strategy_name,
            )

    elif req.side == OrderSide.SELL:
        if req.symbol not in portfolio.positions:
            logger.warning("SELL order for %s ignored — no position held", req.symbol)
            return
        pos = portfolio.positions[req.symbol]
        sell_amount = min(req.amount, pos.amount)
        sell_notional = sell_amount * price
        portfolio.balance_quote += sell_notional
        remaining = pos.amount - sell_amount
        if remaining <= 0:
            del portfolio.positions[req.symbol]
        else:
            portfolio.positions[req.symbol] = pos.model_copy(update={"amount": remaining})


def _rollback_portfolio(
    portfolio: Portfolio,
    snapshot: Portfolio | None,
    state: CycleState,
) -> None:
    """Restore portfolio from snapshot if tentative reservations were applied.

    Called when execution is skipped or fails, so unconfirmed order requests
    don't pollute risk state for the next cycle.
    """
    if snapshot is None or not state.order_requests:
        return
    portfolio.balance_quote = snapshot.balance_quote
    portfolio.positions = snapshot.positions
    portfolio.peak_balance = snapshot.peak_balance
    logger.info(
        "Rolled back tentative portfolio reservations (%d order requests discarded)",
        len(state.order_requests),
    )


def main() -> None:
    """Main entry point — initialize services and run the scaffold trading loop."""
    settings = get_settings()
    _setup_logging(settings.log_level)

    logger.info("=" * 60)
    logger.info("Trading Crew v0.6.0 starting (Phase 6: Backtesting Engine)")
    logger.info("Mode: %s", settings.trading_mode.value)
    logger.info("Exchange: %s (sandbox=%s)", settings.exchange_id, settings.exchange_sandbox)
    logger.info("Symbols: %s", ", ".join(settings.symbols))
    logger.info("Loop interval: %ds", settings.loop_interval_seconds)
    logger.info("Market pipeline mode: %s", settings.market_pipeline_mode.value)
    logger.info(
        "Market regime thresholds: volatility=%.4f, trend=%.4f",
        settings.market_regime_volatility_threshold,
        settings.market_regime_trend_threshold,
    )
    logger.info("Sentiment enrichment enabled: %s", settings.sentiment_enabled)
    logger.info("Strategy pipeline mode: %s", settings.strategy_pipeline_mode.value)
    logger.info("Execution pipeline mode: %s", settings.execution_pipeline_mode.value)
    logger.info(
        "Stale order cancel: %dmin (partial fills: %dmin)",
        settings.stale_order_cancel_minutes,
        settings.stale_partial_fill_cancel_minutes,
    )
    logger.info("Ensemble mode: %s", settings.ensemble_enabled)
    logger.info(
        "Stop-loss method: %s (ATR multiplier=%.1f)",
        settings.stop_loss_method.value,
        settings.atr_stop_multiplier,
    )
    logger.info("Initial balance: %.2f", settings.initial_balance_quote)
    logger.info("Cost contention mode: %s", settings.cost_contention_enabled)
    if settings.cost_contention_enabled:
        logger.info(
            "Crew intervals (market=%ds, strategy=%ds, execution=%ds)",
            settings.market_crew_interval_seconds,
            settings.strategy_crew_interval_seconds,
            settings.execution_crew_interval_seconds,
        )
    logger.info("Daily token budget enabled: %s", settings.daily_token_budget_enabled)
    if settings.daily_token_budget_enabled:
        logger.info(
            "Daily token budget: %d (estimates: market=%d, strategy=%d, execution=%d)",
            settings.daily_token_budget_tokens,
            settings.market_crew_estimated_tokens,
            settings.strategy_crew_estimated_tokens,
            settings.execution_crew_estimated_tokens,
        )
        logger.info(
            "Budget degrade mode: %s (non_llm_monitor_on_hard_stop=%s)",
            settings.token_budget_degrade_mode.value,
            settings.non_llm_monitor_on_hard_stop,
        )
    logger.info("=" * 60)

    if settings.is_live:
        logger.warning("LIVE TRADING MODE — real orders will be placed on %s", settings.exchange_id)

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    # -- Initialize services --------------------------------------------------
    engine = get_engine(settings.database_url)
    init_db(engine)

    exchange_service = ExchangeService(
        exchange_id=settings.exchange_id,
        api_key=settings.exchange_api_key,
        api_secret=settings.exchange_api_secret,
        password=settings.exchange_password,
        sandbox=settings.exchange_sandbox,
        paper_mode=settings.is_paper,
    )

    db_service = DatabaseService(settings.database_url)
    sentiment_service = (
        SentimentService(
            fear_greed_enabled=settings.sentiment_fear_greed_enabled,
            fear_greed_weight=settings.sentiment_fear_greed_weight,
            timeout_seconds=settings.sentiment_request_timeout_seconds,
        )
        if settings.sentiment_enabled
        else None
    )
    market_intelligence_service = MarketIntelligenceService(
        exchange_service,
        db_service,
        sentiment_service=sentiment_service,
        regime_volatility_threshold=settings.market_regime_volatility_threshold,
        regime_trend_threshold=settings.market_regime_trend_threshold,
    )
    notification_service = NotificationService.from_settings()
    circuit_breaker = CircuitBreaker(settings.risk)

    # -- Strategy + Risk pipeline (Phase 3) -----------------------------------
    strategies = [
        EMACrossoverStrategy(),
        BollingerBandsStrategy(),
        RSIRangeStrategy(),
    ]
    strategy_runner = StrategyRunner(
        strategies=strategies,
        min_confidence=settings.risk.min_confidence,
        ensemble=settings.ensemble_enabled,
        ensemble_agreement_threshold=settings.ensemble_agreement_threshold,
    )
    logger.info("Strategies loaded: %s", ", ".join(strategy_runner.strategy_names))
    risk_pipeline = RiskPipeline(
        risk_params=settings.risk,
        circuit_breaker=circuit_breaker,
        stop_loss_method=settings.stop_loss_method.value,
        atr_stop_multiplier=settings.atr_stop_multiplier,
    )
    execution_service = ExecutionService(
        exchange_service=exchange_service,
        db_service=db_service,
        notification_service=notification_service,
        stale_order_cancel_minutes=settings.stale_order_cancel_minutes,
        stale_partial_fill_cancel_minutes=settings.stale_partial_fill_cancel_minutes,
    )

    portfolio = Portfolio(
        balance_quote=settings.initial_balance_quote,
        peak_balance=settings.initial_balance_quote,
    )

    # -- Load YAML configs ----------------------------------------------------
    agent_configs = _load_yaml(str(settings.agents_yaml_path))
    task_configs = _load_yaml(str(settings.tasks_yaml_path))

    # -- Create agents --------------------------------------------------------
    sentinel = create_sentinel_agent(
        exchange_service, db_service, agent_configs.get("sentinel", {})
    )
    analyst = create_analyst_agent(agent_configs.get("analyst", {}))
    sentiment = create_sentiment_agent(agent_configs.get("sentiment", {}))
    strategist = create_strategist_agent(
        agent_configs.get("strategist", {}),
        strategy_runner=strategy_runner,
    )
    risk_manager = create_risk_manager_agent(
        agent_configs.get("risk_manager", {}),
        risk_pipeline=risk_pipeline,
        portfolio=portfolio,
    )
    executor = create_executor_agent(
        exchange_service,
        notification_service,
        agent_configs.get("executor", {}),
        db_service=db_service,
    )
    monitor = create_monitor_agent(
        notification_service,
        agent_configs.get("monitor", {}),
        exchange_service=exchange_service,
        db_service=db_service,
    )

    # -- Build crews ----------------------------------------------------------
    market_crew = MarketCrew(
        sentinel=sentinel,
        analyst=analyst,
        sentiment=sentiment,
        task_configs=task_configs,
        symbols=settings.symbols,
        exchange_id=settings.exchange_id,
        timeframe=settings.default_timeframe,
    ).build()

    strategy_crew = StrategyCrew(
        strategist=strategist,
        risk_manager=risk_manager,
        task_configs=task_configs,
        risk_params=settings.risk,
    ).build()

    execution_crew = ExecutionCrew(
        executor=executor,
        monitor=monitor,
        task_configs=task_configs,
        stale_order_cancel_minutes=settings.stale_order_cancel_minutes,
    ).build()

    # -- Notify startup -------------------------------------------------------
    notification_service.notify(
        f"Trading Crew started in *{settings.trading_mode.value}* mode\n"
        f"Exchange: {settings.exchange_id}\n"
        f"Symbols: {', '.join(settings.symbols)}"
    )

    # -- Trading loop ---------------------------------------------------------
    logger.info("Entering trading loop (Ctrl+C to stop)...")
    cycle = 0
    last_market_run: float | None = None
    last_strategy_run: float | None = None
    last_execution_run: float | None = None
    budget_state = BudgetRuntimeState(token_budget_day=_utc_today())
    # Cross-cycle cache: most recent market analyses, used as a stop-loss
    # price fallback when the market phase is skipped this cycle.
    last_market_analyses: dict = {}

    while not _shutdown_requested:
        cycle += 1
        logger.info("--- Cycle %d ---", cycle)

        try:
            _refresh_budget_day(settings, budget_state)
            now = time.monotonic()
            plan = _build_run_plan(
                settings,
                db_service,
                now,
                last_market_run,
                last_strategy_run,
                last_execution_run,
            )
            _update_degrade_level(settings, budget_state, notification_service)
            plan = _apply_degrade_to_plan(settings, budget_state, plan)

            flow = TradingFlow(
                cycle_number=cycle,
                symbols=settings.symbols,
                plan=plan,
                portfolio=portfolio,
                budget_state=budget_state,
                cached_analyses=last_market_analyses,
                circuit_breaker=circuit_breaker,
                market_svc=market_intelligence_service,
                strategy_runner=strategy_runner,
                risk_pipeline=risk_pipeline,
                execution_service=execution_service,
                db_service=db_service,
                notif_service=notification_service,
                market_crew=market_crew,
                strategy_crew=strategy_crew,
                execution_crew=execution_crew,
                settings=settings,
            )
            flow.kickoff()

            # Update cross-cycle market analysis cache from this cycle's state
            if plan.run_market and flow.state.market_analyses:
                last_market_analyses = flow.state.market_analyses

            # Update interval timestamps based on what actually ran
            if plan.run_market:
                last_market_run = now
            if plan.run_strategy:
                last_strategy_run = now
            if plan.run_execution:
                last_execution_run = now

            _accumulate_estimated_tokens(
                settings,
                budget_state,
                ran_market=plan.run_market,
                ran_strategy=plan.run_strategy,
                ran_execution=plan.run_execution,
            )

            if settings.daily_token_budget_enabled:
                logger.info(
                    "Estimated tokens today (UTC): %d / %d [degrade=%s]",
                    budget_state.estimated_tokens_used_today,
                    settings.daily_token_budget_tokens,
                    budget_state.degrade_level.value,
                )

        except KeyboardInterrupt:
            break
        except Exception:
            logger.exception("Error in trading cycle %d", cycle)
            notification_service.notify_error(f"Error in cycle {cycle}")

        if not _shutdown_requested:
            logger.debug("Sleeping %ds until next cycle...", settings.loop_interval_seconds)
            time.sleep(settings.loop_interval_seconds)

    # -- Shutdown -------------------------------------------------------------
    logger.info("Shutting down gracefully...")
    try:
        db_service.save_portfolio(portfolio)
        logger.info("Final portfolio state persisted.")
    except Exception:
        logger.exception("Failed to persist portfolio on shutdown")
    notification_service.notify("Trading Crew stopped.")
    logger.info("Goodbye.")


if __name__ == "__main__":
    main()
