"""Trading Crew — main entry point.

Initializes all services and runs the deterministic-first trading loop with
condition-triggered advisory crew activation.

  Each cycle is orchestrated by ``TradingFlow`` — a CrewAI Flow that wires
  market intelligence, strategy evaluation, uncertainty scoring, optional
  advisory review, order reservation, and execution phases.

  main() retains only the inter-cycle concerns:
    - budget refresh and advisory token accumulation
    - execution poll interval scheduling
    - sleep between cycles
    - cross-cycle state (market-analysis cache, previous regimes)
    - graceful shutdown and final portfolio persistence

Usage:
    trading-crew              # via installed script
    python -m trading_crew.main
    make paper-trade
"""

from __future__ import annotations

import asyncio
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
    from collections.abc import Callable

    from trading_crew.models.cycle import CycleState
    from trading_crew.models.market import MarketAnalysis

from trading_crew.agents.risk_manager import create_risk_advisor
from trading_crew.agents.sentiment import create_sentiment_advisor
from trading_crew.agents.strategist import create_context_advisor
from trading_crew.config import runtime_flags
from trading_crew.config.settings import (
    SellGuardMode,
    Settings,
    TokenBudgetDegradeMode,
    get_settings,
)
from trading_crew.crews.advisory_crew import AdvisoryCrew
from trading_crew.db.session import get_engine, init_db
from trading_crew.flows.trading_flow import TradingFlow
from trading_crew.models.order import OrderRequest, OrderSide
from trading_crew.models.portfolio import Portfolio, Position
from trading_crew.risk.circuit_breaker import CircuitBreaker
from trading_crew.risk.sell_guard import AllowAllSellGuard, BreakEvenSellGuard
from trading_crew.services.database_service import DatabaseService
from trading_crew.services.exchange_service import ExchangeCircuitBreakerError, ExchangeService
from trading_crew.services.execution_service import ExecutionService
from trading_crew.services.market_intelligence_service import MarketIntelligenceService
from trading_crew.services.notification_service import NotificationService
from trading_crew.services.risk_pipeline import RiskPipeline
from trading_crew.services.sentiment_service import SentimentService
from trading_crew.services.strategy_runner import StrategyRunner
from trading_crew.services.uncertainty_scorer import UncertaintyScorer, UncertaintyWeights
from trading_crew.strategies.bollinger import BollingerBandsStrategy
from trading_crew.strategies.ema_crossover import EMACrossoverStrategy
from trading_crew.strategies.rsi_range import RSIRangeStrategy

logger = logging.getLogger("trading_crew")


class BudgetDegradeLevel(StrEnum):
    """Runtime degrade stage.  NORMAL allows advisory; BUDGET_STOP disables it."""

    NORMAL = "normal"
    BUDGET_STOP = "budget_stop"


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


class _LoggingStream:
    """File-like wrapper that routes write() calls through the logging system.

    Installed as ``sys.stdout`` so that any library using ``print()``
    (e.g. CrewAI's EventsBus / ConsoleFormatter) goes through structured
    logging instead of raw console output.  Encoding issues on Windows
    (charmap/cp1252 vs emoji) are eliminated because the underlying
    log handlers already use UTF-8.
    """

    def __init__(self, logger_name: str = "crewai.console", level: int = logging.INFO) -> None:
        self._logger = logging.getLogger(logger_name)
        self._level = level
        self._buffer = ""
        self.encoding = "utf-8"

    def write(self, msg: str) -> int:
        if msg and msg.strip():
            for line in msg.rstrip("\n").split("\n"):
                self._logger.log(self._level, "%s", line)
        return len(msg)

    def flush(self) -> None:
        pass

    def fileno(self) -> int:
        raise OSError("LoggingStream has no file descriptor")

    def isatty(self) -> bool:
        return False


def _setup_logging(level: str, *, capture_stdout: bool = True) -> None:
    """Configure structured logging for the application.

    Args:
        level: Log level string (e.g. "INFO", "DEBUG").
        capture_stdout: When True, replace ``sys.stdout`` with a logging
            wrapper so that third-party ``print()`` calls (CrewAI) flow
            through the logging system.
    """
    # On Windows, ensure the real console streams accept UTF-8 before we
    # hand them off to logging StreamHandler (needed when capture_stdout
    # is False or for stderr).
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")

    log_level = getattr(logging, level.upper(), logging.INFO)
    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("trading_crew.log", encoding="utf-8"),
    ]
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )

    if capture_stdout:
        sys.stdout = _LoggingStream(level=logging.DEBUG)


def _make_shutdown_handler(
    shutdown_event: asyncio.Event, loop: asyncio.AbstractEventLoop
) -> Callable[[int, object], None]:
    """Return a cross-platform SIGINT/SIGTERM handler that sets an asyncio.Event.

    Uses ``loop.call_soon_threadsafe`` so the event is set safely from the
    signal handler context (which may run on a different thread on some
    platforms). This avoids ``loop.add_signal_handler`` which is Unix-only and
    raises ``NotImplementedError`` on Windows.
    """

    def _handle(signum: int, frame: object) -> None:
        logger.info("Shutdown requested (signal %d). Finishing current cycle...", signum)
        loop.call_soon_threadsafe(shutdown_event.set)

    return _handle


async def _sync_balance_if_due(
    exchange: ExchangeService,
    portfolio: Portfolio,
    quote_currency: str,
    interval_seconds: int,
    drift_alert_threshold_pct: float,
    notifier: NotificationService,
    last_sync: datetime,
) -> datetime:
    """Sync portfolio.balance_quote from the exchange if the interval has elapsed.

    Runs as a pre-cycle step so it never races with fill reconciliation.
    Returns the updated last_sync timestamp (unchanged if interval not yet due).
    """
    if (datetime.now(UTC) - last_sync).total_seconds() < interval_seconds:
        return last_sync
    try:
        balances = await exchange.fetch_balance()
        new_balance = balances.get(quote_currency)
        if new_balance is None:
            logger.warning("Balance sync: %s not found in exchange response", quote_currency)
            return datetime.now(UTC)
        old_balance = portfolio.balance_quote
        if abs(new_balance - old_balance) >= 0.01:
            signed_pct = (new_balance - old_balance) / max(old_balance, 1.0) * 100
            drift_pct = abs(signed_pct)
            portfolio.balance_quote = new_balance
            logger.info(
                "Balance sync %s: %.4f → %.4f (%+.2f%%)",
                quote_currency,
                old_balance,
                new_balance,
                signed_pct,
            )
            if drift_pct >= drift_alert_threshold_pct:
                notifier.notify(
                    f"Balance sync: {quote_currency} {old_balance:.4f} → "
                    f"{new_balance:.4f} ({signed_pct:+.2f}%)"
                )
        else:
            logger.debug(
                "Balance sync %s: no meaningful change (%.4f)", quote_currency, old_balance
            )
    except Exception as exc:
        logger.warning("Balance sync failed: %s", exc)
    return datetime.now(UTC)


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
    last_execution_poll: float | None,
) -> RunPlan:
    """Compute the run plan for this cycle.

    Market and strategy always run.  Execution runs when there are new order
    requests OR when the execution poll interval is due and open orders exist.
    """
    plan = RunPlan()
    plan.run_market = True
    plan.run_strategy = True

    execution_due = _is_due(now, last_execution_poll, settings.execution_poll_interval_seconds)
    if execution_due:
        plan.open_orders_count = db_service.count_open_orders()
        plan.run_execution = True
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
    """Advance degrade level when advisory token budget is exhausted."""
    if not settings.daily_token_budget_enabled:
        return

    if (
        settings.token_budget_degrade_mode == TokenBudgetDegradeMode.BUDGET_STOP
        and budget_state.degrade_level == BudgetDegradeLevel.NORMAL
        and budget_state.estimated_tokens_used_today >= settings.daily_token_budget_tokens
    ):
        budget_state.degrade_level = BudgetDegradeLevel.BUDGET_STOP
        logger.warning(
            "Advisory budget stop: estimated tokens=%d >= budget=%d. "
            "Advisory crew disabled for the rest of the UTC day.",
            budget_state.estimated_tokens_used_today,
            settings.daily_token_budget_tokens,
        )
        _notify_budget_breach_once(
            budget_state,
            notification_service,
            "Daily token budget exhausted. Advisory crew disabled until UTC day reset.",
        )


def _accumulate_estimated_tokens(
    settings: Settings,
    budget_state: BudgetRuntimeState,
    advisory_ran: bool,
) -> None:
    """Increment estimated token usage when the advisory crew ran."""
    if not settings.daily_token_budget_enabled:
        return
    if advisory_ran:
        budget_state.estimated_tokens_used_today += settings.advisory_estimated_tokens


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


async def main_async() -> None:
    """Async main entry point — initialize services and run the trading loop."""
    settings = get_settings()
    _setup_logging(settings.log_level, capture_stdout=not settings.crewai_verbose)

    logger.info("=" * 60)
    logger.info("Trading Crew starting (Advisory Architecture)")
    logger.info("Mode: %s", settings.trading_mode.value)
    logger.info("Exchange: %s (sandbox=%s)", settings.exchange_id, settings.exchange_sandbox)
    logger.info("Symbols: %s", ", ".join(settings.symbols))
    logger.info("Loop interval: %ds", settings.loop_interval_seconds)
    logger.info(
        "Market regime thresholds: volatility=%.4f, trend=%.4f",
        settings.market_regime_volatility_threshold,
        settings.market_regime_trend_threshold,
    )
    logger.info("Sentiment enrichment enabled: %s", settings.sentiment_enabled)
    logger.info(
        "Advisory: enabled=%s, threshold=%.2f, estimated_tokens=%d",
        settings.advisory_enabled,
        settings.advisory_activation_threshold,
        settings.advisory_estimated_tokens,
    )
    logger.info("Execution poll interval: %ds", settings.execution_poll_interval_seconds)
    logger.info("Ensemble mode: %s", settings.ensemble_enabled)
    logger.info(
        "Stop-loss method: %s (ATR multiplier=%.1f)",
        settings.stop_loss_method.value,
        settings.atr_stop_multiplier,
    )
    logger.info(
        "Balance source: %s",
        "exchange wallet (live)"
        if settings.is_live
        else f"config ({settings.initial_balance_quote:.2f})",
    )
    logger.info("Daily token budget enabled: %s", settings.daily_token_budget_enabled)
    if settings.daily_token_budget_enabled:
        logger.info(
            "Daily token budget: %d (advisory estimated: %d per activation)",
            settings.daily_token_budget_tokens,
            settings.advisory_estimated_tokens,
        )
    logger.info("=" * 60)

    if settings.is_live:
        logger.warning("LIVE TRADING MODE — real orders will be placed on %s", settings.exchange_id)

    shutdown_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    _handle_shutdown = _make_shutdown_handler(shutdown_event, loop)
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
    sell_guard = (
        BreakEvenSellGuard()
        if settings.sell_guard_mode == SellGuardMode.BREAK_EVEN
        else AllowAllSellGuard()
    )
    risk_pipeline = RiskPipeline(
        risk_params=settings.risk,
        circuit_breaker=circuit_breaker,
        stop_loss_method=settings.stop_loss_method.value,
        atr_stop_multiplier=settings.atr_stop_multiplier,
        anti_averaging_down=settings.anti_averaging_down,
        sell_guard=sell_guard,
    )
    execution_service = ExecutionService(
        exchange_service=exchange_service,
        db_service=db_service,
        notification_service=notification_service,
        stale_order_cancel_minutes=settings.stale_order_cancel_minutes,
        stale_partial_fill_cancel_minutes=settings.stale_partial_fill_cancel_minutes,
        anti_averaging_down_enabled=settings.anti_averaging_down,
    )

    # -- Seed portfolio balance -----------------------------------------------
    if settings.is_live:
        try:
            live_balances = await exchange_service.fetch_balance()
        except ExchangeCircuitBreakerError as exc:
            raise RuntimeError(
                "Live mode: exchange circuit breaker is open — cannot fetch wallet balance. "
                f"Wait for the cooldown or restart. Detail: {exc}"
            ) from exc
        seed_balance = live_balances.get(settings.quote_currency, 0.0)
        if seed_balance <= 0:
            raise RuntimeError(
                f"Live mode: {settings.quote_currency} balance is zero or unavailable. "
                "Check API credentials, permissions, and account funding."
            )
        logger.info(
            "Live balance seeded from exchange: %.4f %s",
            seed_balance,
            settings.quote_currency,
        )
    else:
        seed_balance = settings.initial_balance_quote
        logger.info(
            "Paper balance seeded from config: %.4f %s",
            seed_balance,
            settings.quote_currency,
        )

    portfolio = Portfolio(balance_quote=seed_balance, peak_balance=seed_balance)
    db_service.save_portfolio(portfolio)

    # -- Load YAML configs ----------------------------------------------------
    agent_configs = _load_yaml(str(settings.agents_yaml_path))
    task_configs = _load_yaml(str(settings.tasks_yaml_path))

    # -- Uncertainty scorer ---------------------------------------------------
    uncertainty_scorer = UncertaintyScorer(
        weights=UncertaintyWeights(
            volatile_regime=settings.uncertainty_weight_volatile_regime,
            sentiment_extreme=settings.uncertainty_weight_sentiment_extreme,
            low_sentiment_confidence=settings.uncertainty_weight_low_sentiment_confidence,
            strategy_disagreement=settings.uncertainty_weight_strategy_disagreement,
            drawdown_proximity=settings.uncertainty_weight_drawdown_proximity,
            regime_change=settings.uncertainty_weight_regime_change,
        ),
        activation_threshold=settings.advisory_activation_threshold,
    )

    # -- Advisory crew (optional) ---------------------------------------------
    advisory_crew: AdvisoryCrew | None = None
    if settings.advisory_enabled and settings.openai_api_key:
        _verbose = settings.crewai_verbose
        context_advisor = create_context_advisor(
            agent_configs.get("context_advisor", {}), verbose=_verbose
        )
        risk_advisor = create_risk_advisor(agent_configs.get("risk_advisor", {}), verbose=_verbose)
        sentiment_advisor = create_sentiment_advisor(
            agent_configs.get("sentiment_advisor", {}), verbose=_verbose
        )
        advisory_crew = AdvisoryCrew(
            context_advisor=context_advisor,
            risk_advisor=risk_advisor,
            sentiment_advisor=sentiment_advisor,
            task_configs=task_configs,
        )
        logger.info("Advisory crew initialized (3 agents)")
    else:
        logger.info(
            "Advisory crew disabled (advisory_enabled=%s, api_key_set=%s)",
            settings.advisory_enabled,
            bool(settings.openai_api_key),
        )

    # -- Notify startup -------------------------------------------------------
    notification_service.notify(
        f"Trading Crew started in *{settings.trading_mode.value}* mode\n"
        f"Exchange: {settings.exchange_id}\n"
        f"Symbols: {', '.join(settings.symbols)}"
    )

    # -- Trading loop ---------------------------------------------------------
    logger.info("Entering trading loop (Ctrl+C to stop)...")
    cycle = 0
    last_execution_poll: float | None = None
    budget_state = BudgetRuntimeState(token_budget_day=_utc_today())
    last_market_analyses: dict[str, MarketAnalysis] = {}
    previous_regimes: dict[str, str] = {}
    last_balance_sync: datetime = datetime.now(UTC)

    while not shutdown_event.is_set():
        cycle += 1
        logger.info("--- Cycle %d ---", cycle)

        try:
            # Re-read runtime control flags each cycle so dashboard toggles
            # take effect without a restart.
            rt_flags = runtime_flags.read()
            logger.debug(
                "Runtime flags: execution_paused=%s, advisory_paused=%s",
                rt_flags["execution_paused"],
                rt_flags["advisory_paused"],
            )

            if settings.is_live and settings.balance_sync_interval_seconds > 0:
                last_balance_sync = await _sync_balance_if_due(
                    exchange_service,
                    portfolio,
                    settings.quote_currency,
                    settings.balance_sync_interval_seconds,
                    settings.balance_drift_alert_threshold_pct,
                    notification_service,
                    last_balance_sync,
                )

            _refresh_budget_day(settings, budget_state)
            now = time.monotonic()
            plan = _build_run_plan(settings, db_service, now, last_execution_poll)

            # Apply dashboard execution-pause toggle
            if rt_flags["execution_paused"]:
                logger.warning(
                    "Execution paused via dashboard — skipping execution phase this cycle."
                )
                plan.run_execution = False

            _update_degrade_level(settings, budget_state, notification_service)

            # Pass advisory_paused flag to the flow so it can skip advisory crew
            _effective_advisory_crew = None if rt_flags["advisory_paused"] else advisory_crew
            if rt_flags["advisory_paused"] and advisory_crew is not None:
                logger.warning(
                    "Advisory crew paused via dashboard — skipping advisory phase this cycle."
                )

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
                uncertainty_scorer=uncertainty_scorer,
                advisory_crew=_effective_advisory_crew,
                previous_regimes=previous_regimes,
                settings=settings,
            )
            await flow.akickoff()

            if plan.run_market and flow.state.market_analyses:
                last_market_analyses = flow.state.market_analyses
                previous_regimes = {
                    sym: a.metadata.market_regime or "unknown"
                    for sym, a in flow.state.market_analyses.items()
                }

            if plan.run_execution:
                last_execution_poll = now

            _accumulate_estimated_tokens(
                settings,
                budget_state,
                advisory_ran=flow.state.advisory_ran,
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

        if not shutdown_event.is_set():
            logger.debug("Sleeping %ds until next cycle...", settings.loop_interval_seconds)
            await asyncio.sleep(settings.loop_interval_seconds)

    # -- Shutdown -------------------------------------------------------------
    logger.info("Shutting down gracefully...")
    try:
        db_service.save_portfolio(portfolio)
        logger.info("Final portfolio state persisted.")
    except Exception:
        logger.exception("Failed to persist portfolio on shutdown")
    try:
        await exchange_service.close()
    except Exception:
        logger.exception("Failed to close exchange connection")
    notification_service.notify("Trading Crew stopped.")
    logger.info("Goodbye.")


def main() -> None:
    """Synchronous entry point — wraps the async main in an event loop."""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
