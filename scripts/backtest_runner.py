#!/usr/bin/env python3
"""CLI runner for the backtesting engine.

Usage examples:
    # Basic run (data must already be in the database):
    python scripts/backtest_runner.py --symbol BTC/USDT --exchange binance \\
        --timeframe 1h --from-date 2024-01-01 --to-date 2024-12-31

    # Fetch fresh data then run:
    python scripts/backtest_runner.py --symbol BTC/USDT --exchange binance \\
        --timeframe 1h --from-date 2024-01-01 --to-date 2024-12-31 --fetch

    # Compare all built-in strategies and export results:
    python scripts/backtest_runner.py --symbol BTC/USDT --exchange binance \\
        --timeframe 1h --from-date 2024-01-01 --to-date 2024-12-31 \\
        --compare --output results.json

    # Data-prep only (fetch and cache, no backtest):
    python scripts/backtest_runner.py --symbol BTC/USDT --exchange binance \\
        --timeframe 1h --from-date 2024-01-01 --to-date 2024-12-31 \\
        --fetch --data-only
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure the project src is importable when running directly.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))


def _parse_date(value: str) -> datetime:
    """Parse an ISO date string (YYYY-MM-DD) into a UTC-aware datetime."""
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backtest_runner",
        description="Run historical backtests using the trading_crew strategy pipeline.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--symbol", default="BTC/USDT", help="Trading pair")
    parser.add_argument("--exchange", default="binance", help="CCXT exchange ID")
    parser.add_argument("--timeframe", default="1h", help="Candle period (e.g. 1h, 1d)")
    parser.add_argument(
        "--from-date",
        dest="from_date",
        default=None,
        help="Start date (YYYY-MM-DD). Required unless --candles-file is used.",
    )
    parser.add_argument(
        "--to-date",
        dest="to_date",
        default=None,
        help="End date (YYYY-MM-DD). Required unless --candles-file is used.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path to output file (.json or .csv). Omit to print summary only.",
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Fetch OHLCV data from the exchange and cache to DB before running.",
    )
    parser.add_argument(
        "--data-only",
        dest="data_only",
        action="store_true",
        help="Only fetch and cache data; do not run the backtest.",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Run all 3 built-in strategies and rank by Sharpe ratio.",
    )
    parser.add_argument(
        "--slippage",
        type=float,
        default=0.001,
        help="Fill slippage as a fraction (e.g. 0.001 = 0.1%%)",
    )
    parser.add_argument(
        "--fee-rate",
        dest="fee_rate",
        type=float,
        default=0.001,
        help="Taker fee as a fraction (e.g. 0.001 = 0.1%%)",
    )
    parser.add_argument(
        "--initial-balance",
        dest="initial_balance",
        type=float,
        default=10_000.0,
        help="Starting balance in quote currency.",
    )
    parser.add_argument(
        "--advisory-mode",
        dest="advisory_mode",
        choices=["deterministic_only", "with_advisory"],
        default="deterministic_only",
        help="Backtest mode: deterministic_only (default) or with_advisory.",
    )

    # -- Full simulation flags ------------------------------------------------
    parser.add_argument(
        "--simulation",
        action="store_true",
        help="Use SimulationRunner (full TradingFlow) instead of legacy BacktestService.",
    )
    parser.add_argument(
        "--candles-file",
        dest="candles_file",
        default=None,
        help="Load candles from a CSV file (Binance kline format) instead of DB.",
    )
    parser.add_argument(
        "--resample",
        default=None,
        help="Resample CSV candles to a larger timeframe (e.g. 1h, 4h, 1d).",
    )
    parser.add_argument(
        "--max-bars",
        dest="max_bars",
        type=int,
        default=50_000,
        help="Maximum number of bars to process (safety valve).",
    )
    return parser


def main() -> int:
    # Deferred imports so that sys.path.insert above takes effect before any
    # trading_crew module is resolved (avoids E402 and import-order issues).
    from trading_crew.config.settings import get_settings
    from trading_crew.db.session import get_engine
    from trading_crew.models.backtest import BacktestAdvisoryMode, BacktestConfig
    from trading_crew.models.risk import RiskParams
    from trading_crew.services.backtest_service import BacktestService
    from trading_crew.services.database_service import DatabaseService
    from trading_crew.services.exchange_service import ExchangeService
    from trading_crew.services.strategy_runner import StrategyRunner
    from trading_crew.strategies.bollinger import BollingerBandsStrategy
    from trading_crew.strategies.ema_crossover import EMACrossoverStrategy
    from trading_crew.strategies.rsi_range import RSIRangeStrategy

    parser = _build_parser()
    args = parser.parse_args()

    if not args.candles_file and (not args.from_date or not args.to_date):
        print("ERROR: --from-date and --to-date are required unless --candles-file is used.")
        return 1

    from_dt = _parse_date(args.from_date) if args.from_date else None
    to_dt = _parse_date(args.to_date) if args.to_date else None

    if from_dt and to_dt and from_dt >= to_dt:
        print(f"ERROR: --from-date must be before --to-date ({args.from_date} >= {args.to_date})")
        return 1

    settings = get_settings()
    engine = get_engine(settings.database_url)
    db_service = DatabaseService(engine)

    # ---- Optional data fetch ------------------------------------------------
    if args.fetch:
        import asyncio as _asyncio

        print(
            f"Fetching {args.symbol} {args.timeframe} from {args.from_date} to {args.to_date} ..."
        )
        exchange_svc = ExchangeService(
            exchange_id=args.exchange,
            sandbox=False,
        )

        async def _fetch() -> list:
            try:
                return await exchange_svc.fetch_ohlcv_range(
                    symbol=args.symbol,
                    timeframe=args.timeframe,
                    since=from_dt,
                    until=to_dt,
                )
            finally:
                await exchange_svc.close()

        candles = _asyncio.run(_fetch())
        saved = db_service.save_ohlcv_batch(candles)
        print(f"Cached {saved} candles to database.")

        if args.data_only:
            print("Done (--data-only mode).")
            return 0

    # ---- Load candles -------------------------------------------------------
    if args.candles_file:
        from trading_crew.services.candle_loader import load_candles_csv

        candles = load_candles_csv(
            path=args.candles_file,
            symbol=args.symbol,
            exchange=args.exchange,
            timeframe=args.timeframe,
            start=from_dt,
            end=to_dt,
            max_bars=args.max_bars,
            resample=args.resample,
        )
        if not candles:
            print(
                f"ERROR: No candles found in {args.candles_file} "
                f"for [{args.from_date}, {args.to_date}]."
            )
            return 1
        effective_timeframe = args.resample or args.timeframe
        print(
            f"Loaded {len(candles)} candles from CSV "
            f"({candles[0].timestamp.date()} to {candles[-1].timestamp.date()}, "
            f"timeframe={effective_timeframe})"
        )
    else:
        effective_timeframe = args.timeframe
        candles = db_service.get_ohlcv_range(
            symbol=args.symbol,
            exchange=args.exchange,
            timeframe=args.timeframe,
            start=from_dt,
            end=to_dt,
        )
        if not candles:
            print(
                f"ERROR: No candles found for {args.symbol}/{args.exchange}/{args.timeframe} "
                f"in [{args.from_date}, {args.to_date}]. Run with --fetch first."
            )
            return 1
        if len(candles) > args.max_bars:
            candles = candles[: args.max_bars]
            print(f"Truncated to {args.max_bars} bars (--max-bars)")

        print(
            f"Loaded {len(candles)} candles from {candles[0].timestamp.date()} "
            f"to {candles[-1].timestamp.date()}"
        )

    # ---- Build config -------------------------------------------------------
    advisory_mode = BacktestAdvisoryMode(args.advisory_mode)
    config = BacktestConfig(
        initial_balance=args.initial_balance,
        fee_rate=args.fee_rate,
        slippage_pct=args.slippage,
        advisory_mode=advisory_mode,
    )
    risk_params = RiskParams()

    advisory_crew = None
    uncertainty_scorer = None
    if advisory_mode == BacktestAdvisoryMode.WITH_ADVISORY:
        from trading_crew.services.uncertainty_scorer import UncertaintyScorer

        uncertainty_scorer = UncertaintyScorer()
        print("Advisory mode: WITH_ADVISORY (uncertainty scoring enabled)")

    # ---- Build services and run ----------------------------------------------
    if args.simulation:
        import asyncio as _aio

        from trading_crew.services.simulation_runner import SimulationRunner

        def _make_sim_runner(strats: list) -> SimulationRunner:
            return SimulationRunner(
                strategies=strats,
                settings=settings,
                config=config,
                advisory_crew=advisory_crew,
            )

        if args.compare:
            runners = [
                _make_sim_runner([EMACrossoverStrategy()]),
                _make_sim_runner([RSIRangeStrategy()]),
                _make_sim_runner([BollingerBandsStrategy()]),
            ]
            print("\n[Simulation] Comparing: EMA Crossover vs RSI Range vs Bollinger Bands ...\n")
            results = SimulationRunner.compare(
                runners,
                symbol=args.symbol,
                exchange_id=args.exchange,
                candles=candles,
                timeframe=effective_timeframe,
            )
            for rank, result in enumerate(results, 1):
                print(f"  #{rank}: {result.summary()}")
        else:
            strats = [EMACrossoverStrategy(), RSIRangeStrategy(), BollingerBandsStrategy()]
            sim_runner = _make_sim_runner(strats)
            print(f"[Simulation] Running with {len(strats)} strategies ...\n")
            result = _aio.run(
                sim_runner.run(args.symbol, args.exchange, candles, effective_timeframe)
            )
            results = [result]
            print(f"  {result.summary()}")
    else:

        def _make_service(strategies: list) -> BacktestService:
            runner = StrategyRunner(strategies)
            return BacktestService(
                runner,
                risk_params,
                config,
                advisory_crew=advisory_crew,
                uncertainty_scorer=uncertainty_scorer,
            )

        if args.compare:
            services = [
                _make_service([EMACrossoverStrategy()]),
                _make_service([RSIRangeStrategy()]),
                _make_service([BollingerBandsStrategy()]),
            ]
            print("\nRunning comparison: EMA Crossover vs RSI Range vs Bollinger Bands ...\n")
            results = BacktestService.compare(
                services,
                symbol=args.symbol,
                exchange=args.exchange,
                candles=candles,
                timeframe=effective_timeframe,
            )
            for rank, result in enumerate(results, 1):
                print(f"  #{rank}: {result.summary()}")
        else:
            strategies = [EMACrossoverStrategy(), RSIRangeStrategy(), BollingerBandsStrategy()]
            runner = StrategyRunner(strategies, ensemble=False)
            service = BacktestService(
                runner,
                risk_params,
                config,
                advisory_crew=advisory_crew,
                uncertainty_scorer=uncertainty_scorer,
            )
            print(f"Running backtest with {len(strategies)} strategies ...\n")
            results = [service.run(args.symbol, args.exchange, candles, effective_timeframe)]
            print(f"  {results[0].summary()}")

    if results and advisory_mode == BacktestAdvisoryMode.WITH_ADVISORY:
        r = results[0]
        avg_unc = (
            sum(r.uncertainty_scores) / len(r.uncertainty_scores) if r.uncertainty_scores else 0.0
        )
        print(
            f"  Advisory: {r.advisory_activations} activations, "
            f"{r.advisory_vetoes} vetoes, avg uncertainty={avg_unc:.3f}"
        )

    # ---- Export results -----------------------------------------------------
    if args.output and results:
        output_path = args.output
        primary = results[0]
        if output_path.endswith(".csv"):
            primary.to_csv(output_path)
            print(f"\nTrade records exported to {output_path}")
        else:
            if not output_path.endswith(".json"):
                output_path += ".json"
            primary.to_json(output_path)
            print(f"\nFull results exported to {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
