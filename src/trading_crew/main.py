"""Trading Crew — main entry point.

Initializes all services, builds the three crews, and runs the trading loop.
In Phase 1 this is a simple sequential loop; in Phase 5 it will be upgraded
to a CrewAI Flow with event-driven orchestration.

Usage:
    # Via the installed script
    trading-crew

    # Via Python directly
    python -m trading_crew.main

    # Via Makefile
    make paper-trade
"""

from __future__ import annotations

import logging
import signal
import sys
import time

import yaml

from trading_crew.config.settings import get_settings, TradingMode
from trading_crew.db.session import get_engine, init_db
from trading_crew.services.exchange_service import ExchangeService
from trading_crew.services.database_service import DatabaseService
from trading_crew.services.notification_service import NotificationService
from trading_crew.agents.sentinel import create_sentinel_agent
from trading_crew.agents.analyst import create_analyst_agent
from trading_crew.agents.sentiment import create_sentiment_agent
from trading_crew.agents.strategist import create_strategist_agent
from trading_crew.agents.risk_manager import create_risk_manager_agent
from trading_crew.agents.executor import create_executor_agent
from trading_crew.agents.monitor import create_monitor_agent
from trading_crew.crews.market_crew import MarketCrew
from trading_crew.crews.strategy_crew import StrategyCrew
from trading_crew.crews.execution_crew import ExecutionCrew
from trading_crew.risk.circuit_breaker import CircuitBreaker

logger = logging.getLogger("trading_crew")

_shutdown_requested = False


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


def main() -> None:
    """Main entry point — initialize services and run the trading loop."""
    settings = get_settings()
    _setup_logging(settings.log_level)

    logger.info("=" * 60)
    logger.info("Trading Crew v0.1.0 starting")
    logger.info("Mode: %s", settings.trading_mode.value)
    logger.info("Exchange: %s (sandbox=%s)", settings.exchange_id, settings.exchange_sandbox)
    logger.info("Symbols: %s", ", ".join(settings.symbols))
    logger.info("Loop interval: %ds", settings.loop_interval_seconds)
    logger.info("=" * 60)

    if settings.is_live:
        logger.warning(
            "LIVE TRADING MODE — real orders will be placed on %s", settings.exchange_id
        )

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
    notification_service = NotificationService.from_settings()
    circuit_breaker = CircuitBreaker(settings.risk)

    # -- Load YAML configs ----------------------------------------------------
    agent_configs = _load_yaml(str(settings.agents_yaml_path))
    task_configs = _load_yaml(str(settings.tasks_yaml_path))

    # -- Create agents --------------------------------------------------------
    sentinel = create_sentinel_agent(
        exchange_service, db_service, agent_configs.get("sentinel", {})
    )
    analyst = create_analyst_agent(agent_configs.get("analyst", {}))
    sentiment = create_sentiment_agent(agent_configs.get("sentiment", {}))
    strategist = create_strategist_agent(agent_configs.get("strategist", {}))
    risk_manager = create_risk_manager_agent(agent_configs.get("risk_manager", {}))
    executor = create_executor_agent(
        exchange_service, notification_service, agent_configs.get("executor", {})
    )
    monitor = create_monitor_agent(notification_service, agent_configs.get("monitor", {}))

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

    while not _shutdown_requested:
        cycle += 1
        logger.info("--- Cycle %d ---", cycle)

        try:
            if circuit_breaker.is_tripped:
                logger.warning("Circuit breaker is tripped: %s", circuit_breaker.trip_reason)
                logger.warning("Skipping cycle. Manual reset required.")
                time.sleep(settings.loop_interval_seconds)
                continue

            logger.info("[1/3] Running Market Intelligence Crew...")
            market_result = market_crew.kickoff()
            logger.info("Market Crew output: %s", str(market_result)[:200])

            logger.info("[2/3] Running Strategy Crew...")
            strategy_result = strategy_crew.kickoff()
            logger.info("Strategy Crew output: %s", str(strategy_result)[:200])

            logger.info("[3/3] Running Execution Crew...")
            execution_result = execution_crew.kickoff()
            logger.info("Execution Crew output: %s", str(execution_result)[:200])

            logger.info("Cycle %d complete.", cycle)

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
    notification_service.notify("Trading Crew stopped.")
    logger.info("Goodbye.")


if __name__ == "__main__":
    main()
