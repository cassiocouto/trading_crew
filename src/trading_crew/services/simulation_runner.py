"""Full-fidelity simulation runner.

Runs the real ``TradingFlow`` per historical candle against a
``SimulatedExchangeService`` and in-memory SQLite database, producing a
``BacktestResult`` compatible with the legacy ``BacktestService``.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from trading_crew.db.session import init_db
from trading_crew.models.backtest import (
    BacktestConfig,
    BacktestResult,
    BacktestTrade,
    EquityPoint,
)
from trading_crew.models.order import OrderRequest, OrderSide, OrderType
from trading_crew.models.portfolio import Portfolio
from trading_crew.risk.circuit_breaker import CircuitBreaker
from trading_crew.services.database_service import DatabaseService
from trading_crew.services.execution_service import ExecutionService
from trading_crew.services.market_intelligence_service import MarketIntelligenceService
from trading_crew.services.notification_service import NotificationService
from trading_crew.services.risk_pipeline import RiskPipeline
from trading_crew.services.simulated_exchange import SimulatedExchangeService
from trading_crew.services.strategy_runner import StrategyRunner
from trading_crew.services.uncertainty_scorer import UncertaintyScorer

if TYPE_CHECKING:
    from datetime import datetime

    from trading_crew.config.settings import Settings
    from trading_crew.crews.advisory_crew import AdvisoryCrew
    from trading_crew.models.market import OHLCV
    from trading_crew.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)

_TIMEFRAME_SECONDS: dict[str, int] = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "8h": 28800,
    "12h": 43200,
    "1d": 86400,
    "1w": 604800,
}


class SimulationRunner:
    """Run the full ``TradingFlow`` against historical candles.

    Each bar is a cycle:  advance simulated exchange -> run flow -> collect metrics.
    """

    def __init__(
        self,
        strategies: list[BaseStrategy],
        settings: Settings,
        config: BacktestConfig | None = None,
        advisory_crew: AdvisoryCrew | None = None,
    ) -> None:
        self._strategies = strategies
        self._settings = settings
        self._config = config or BacktestConfig()
        self._advisory_crew = advisory_crew

    async def run(
        self,
        symbol: str,
        exchange_id: str,
        candles: list[OHLCV],
        timeframe: str,
    ) -> BacktestResult:
        """Run a full simulation and return a ``BacktestResult``."""
        from trading_crew.flows.trading_flow import TradingFlow
        from trading_crew.main import BudgetRuntimeState, RunPlan

        cfg = self._config
        min_bars = cfg.min_candles_for_analysis
        if len(candles) < min_bars + 1:
            raise ValueError(f"Need at least {min_bars + 1} candles, got {len(candles)}")

        sim_exchange = SimulatedExchangeService(
            candles=candles,
            symbol=symbol,
            exchange_id=exchange_id,
            fee_rate=cfg.fee_rate,
            slippage_pct=cfg.slippage_pct,
        )

        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )
        init_db(engine)
        db_service = DatabaseService(engine)

        notif_service = NotificationService(channels=[], notify_level="all")

        market_svc = MarketIntelligenceService(
            exchange_service=sim_exchange,  # type: ignore[arg-type]
            db_service=db_service,
            sentiment_service=None,
        )
        strategy_runner = StrategyRunner(
            strategies=self._strategies,
            min_confidence=self._settings.risk.min_confidence,
            ensemble=self._settings.ensemble_enabled,
            ensemble_agreement_threshold=self._settings.ensemble_agreement_threshold,
        )
        circuit_breaker = CircuitBreaker(self._settings.risk)
        risk_pipeline = RiskPipeline(
            risk_params=self._settings.risk,
            circuit_breaker=circuit_breaker,
            stop_loss_method=self._settings.stop_loss_method.value,
            atr_stop_multiplier=self._settings.atr_stop_multiplier,
            anti_averaging_down=self._settings.anti_averaging_down,
        )
        execution_service = ExecutionService(
            exchange_service=sim_exchange,  # type: ignore[arg-type]
            db_service=db_service,
            notification_service=notif_service,
        )
        uncertainty_scorer = UncertaintyScorer(
            activation_threshold=self._settings.advisory_activation_threshold,
        )

        portfolio = Portfolio(
            balance_quote=cfg.initial_balance,
            peak_balance=cfg.initial_balance,
        )
        budget_state = BudgetRuntimeState(token_budget_day=date.today())

        equity_curve: list[EquityPoint] = []
        previous_regimes: dict[str, str] = {}
        cached_analyses: dict[str, Any] = {}
        advisory_activations = 0
        advisory_vetoes = 0
        uncertainty_scores: list[float] = []

        candle_limit = min(50, self._settings.market_data_candle_limit)
        settings_copy = self._settings.model_copy(
            update={
                "market_data_candle_limit": candle_limit,
                "symbols": [symbol],
                "advisory_enabled": self._advisory_crew is not None,
                "crewai_verbose": False,
                "save_cycle_history": True,
                "stop_loss_monitoring_enabled": True,
            }
        )

        for i in range(min_bars, len(candles)):
            sim_exchange.advance_bar(i)
            candle = candles[i]

            plan = RunPlan(
                run_market=True,
                run_strategy=True,
                run_execution=True,
            )

            flow = TradingFlow(
                cycle_number=i,
                symbols=[symbol],
                plan=plan,
                portfolio=portfolio,
                budget_state=budget_state,
                cached_analyses=cached_analyses,
                circuit_breaker=circuit_breaker,
                market_svc=market_svc,
                strategy_runner=strategy_runner,
                risk_pipeline=risk_pipeline,
                execution_service=execution_service,
                db_service=db_service,
                notif_service=notif_service,
                uncertainty_scorer=uncertainty_scorer,
                advisory_crew=self._advisory_crew,
                previous_regimes=previous_regimes,
                settings=settings_copy,
            )

            try:
                await flow.akickoff()
            except Exception:
                logger.exception("Simulation flow error at bar %d", i)

            if flow.state.market_analyses:
                cached_analyses = flow.state.market_analyses
                previous_regimes = {
                    sym: a.metadata.market_regime or "unknown"
                    for sym, a in flow.state.market_analyses.items()
                }

            uncertainty_scores.append(flow.state.uncertainty_score)
            if flow.state.advisory_ran:
                advisory_activations += 1
                if not flow.state.signals and flow.state.advisory_adjustments:
                    advisory_vetoes += 1
                else:
                    from trading_crew.models.advisory import AdjustmentAction

                    for adj_dict in flow.state.advisory_adjustments:
                        action = adj_dict.get("action", "")
                        if action in (AdjustmentAction.VETO_SIGNAL, AdjustmentAction.SIT_OUT):
                            advisory_vetoes += 1

            for pos in portfolio.positions.values():
                pos.current_price = candle.close

            unrealized_pnl = sum(p.unrealized_pnl for p in portfolio.positions.values())
            total_balance = portfolio.balance_quote + sum(
                p.amount * (p.current_price or 0) for p in portfolio.positions.values()
            )
            peak = max(getattr(portfolio, "peak_balance", total_balance), total_balance)
            drawdown_pct = ((peak - total_balance) / peak * 100) if peak > 0 else 0.0

            equity_curve.append(
                EquityPoint(
                    timestamp=candle.timestamp,
                    balance=total_balance,
                    unrealized_pnl=unrealized_pnl,
                    drawdown_pct=drawdown_pct,
                )
            )

            if circuit_breaker.is_tripped:
                logger.info("Circuit breaker tripped at bar %d -- halting simulation", i)
                break

        # -- Force-close open positions through ExecutionService ---------------
        if portfolio.positions:
            close_requests: list[OrderRequest] = []
            for sym, pos in list(portfolio.positions.items()):
                close_requests.append(
                    OrderRequest(
                        symbol=sym,
                        exchange=exchange_id,
                        side=OrderSide.SELL,
                        order_type=OrderType.MARKET,
                        amount=pos.amount,
                        strategy_name="end_of_data",
                        signal_confidence=1.0,
                    )
                )
            if close_requests:
                try:
                    await execution_service.process_order_requests(close_requests, portfolio)
                except Exception:
                    logger.exception("Error force-closing positions")

        # -- Build result ------------------------------------------------------
        trades = self._build_trades(db_service, symbol, candles)
        metrics = _compute_metrics(trades, equity_curve, cfg.initial_balance, timeframe)

        return BacktestResult(
            symbol=symbol,
            exchange=exchange_id,
            timeframe=timeframe,
            strategy_names=[s.name for s in self._strategies],
            start_date=candles[min_bars].timestamp,
            end_date=candles[-1].timestamp,
            initial_balance=cfg.initial_balance,
            final_balance=metrics["final_balance"],
            total_return_pct=metrics["total_return_pct"],
            sharpe_ratio=metrics["sharpe_ratio"],
            max_drawdown_pct=metrics["max_drawdown_pct"],
            win_rate_pct=metrics["win_rate_pct"],
            profit_factor=metrics["profit_factor"],
            total_trades=int(metrics["winning_trades"] + metrics["losing_trades"]),
            winning_trades=int(metrics["winning_trades"]),
            losing_trades=int(metrics["losing_trades"]),
            total_fees=metrics["total_fees"],
            trades=trades,
            equity_curve=equity_curve,
            advisory_activations=advisory_activations,
            advisory_vetoes=advisory_vetoes,
            uncertainty_scores=uncertainty_scores,
        )

    def _build_trades(
        self, db_service: DatabaseService, symbol: str, candles: list[OHLCV]
    ) -> list[BacktestTrade]:
        """Reconstruct trade list from DB order records."""
        from trading_crew.db.models import OrderRecord
        from trading_crew.db.session import get_session

        ts_to_bar: dict[float, int] = {}
        for idx, c in enumerate(candles):
            ts_to_bar[c.timestamp.timestamp()] = idx

        def _nearest_bar(dt: datetime | None) -> int:
            if dt is None:
                return 0
            target = dt.timestamp()
            best_bar = 0
            best_dist = float("inf")
            for ts_val, bar in ts_to_bar.items():
                dist = abs(ts_val - target)
                if dist < best_dist:
                    best_dist = dist
                    best_bar = bar
            return best_bar

        trades: list[BacktestTrade] = []
        with get_session(db_service._engine) as session:
            orders = (
                session.query(OrderRecord)
                .filter(OrderRecord.status == "filled")
                .order_by(OrderRecord.created_at)
                .all()
            )

            buy_orders: dict[str, OrderRecord] = {}
            for order in orders:
                if order.side == "buy":
                    buy_orders[order.symbol] = order
                elif order.side == "sell" and order.symbol in buy_orders:
                    buy_order = buy_orders.pop(order.symbol)
                    entry_price = buy_order.average_fill_price or 0.0
                    exit_price = order.average_fill_price or 0.0
                    amount = buy_order.filled_amount or 0.0
                    entry_fee = buy_order.total_fee or 0.0
                    exit_fee = order.total_fee or 0.0
                    pnl = (exit_price - entry_price) * amount - entry_fee - exit_fee

                    exit_reason = "sell_signal"
                    if order.strategy_name == "end_of_data":
                        exit_reason = "end_of_data"

                    trades.append(
                        BacktestTrade(
                            symbol=order.symbol,
                            side="buy",
                            strategy_name=buy_order.strategy_name or "",
                            entry_bar=_nearest_bar(buy_order.created_at),
                            exit_bar=_nearest_bar(order.created_at),
                            entry_price=entry_price,
                            exit_price=exit_price,
                            amount=amount,
                            pnl=pnl,
                            fee=entry_fee + exit_fee,
                            exit_reason=exit_reason,
                            opened_at=buy_order.created_at,
                            closed_at=order.created_at,
                        )
                    )
        return trades

    @staticmethod
    def compare(
        runners: list[SimulationRunner],
        symbol: str,
        exchange_id: str,
        candles: list[OHLCV],
        timeframe: str,
    ) -> list[BacktestResult]:
        """Run multiple simulation configurations and return results sorted by Sharpe."""
        results: list[BacktestResult] = []
        for runner in runners:
            result = asyncio.run(runner.run(symbol, exchange_id, candles, timeframe))
            results.append(result)
        results.sort(
            key=lambda r: r.sharpe_ratio if not math.isnan(r.sharpe_ratio) else float("-inf"),
            reverse=True,
        )
        return results


def _compute_metrics(
    trades: list[BacktestTrade],
    equity_curve: list[EquityPoint],
    initial_balance: float,
    timeframe: str = "1h",
) -> dict[str, float]:
    """Compute aggregate performance metrics (mirrors BacktestService logic)."""
    final_balance = equity_curve[-1].balance if equity_curve else initial_balance
    total_return_pct = ((final_balance - initial_balance) / initial_balance) * 100

    max_drawdown_pct = max((p.drawdown_pct for p in equity_curve), default=0.0)

    winning = [t for t in trades if t.pnl > 0]
    losing = [t for t in trades if t.pnl <= 0]
    win_rate_pct = (len(winning) / len(trades) * 100) if trades else 0.0

    gross_profit = sum(t.pnl for t in winning)
    gross_loss = abs(sum(t.pnl for t in losing))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    total_fees = sum(t.fee for t in trades)

    seconds = _TIMEFRAME_SECONDS.get(timeframe, _TIMEFRAME_SECONDS["1h"])
    periods_per_year = (365 * 24 * 3600) / seconds
    ann_factor = math.sqrt(periods_per_year)

    sharpe = float("nan")
    if len(equity_curve) >= 2:
        balances = [p.balance for p in equity_curve]
        returns: list[float] = []
        for j in range(1, len(balances)):
            if balances[j - 1] > 0:
                returns.append((balances[j] - balances[j - 1]) / balances[j - 1])
        if len(returns) >= 2:
            n = len(returns)
            mean_r = sum(returns) / n
            variance = sum((r - mean_r) ** 2 for r in returns) / (n - 1)
            std_r = math.sqrt(variance) if variance > 0 else 0.0
            sharpe = (mean_r / std_r * ann_factor) if std_r > 0 else 0.0

    return {
        "final_balance": final_balance,
        "total_return_pct": total_return_pct,
        "sharpe_ratio": sharpe,
        "max_drawdown_pct": max_drawdown_pct,
        "win_rate_pct": win_rate_pct,
        "profit_factor": profit_factor,
        "winning_trades": float(len(winning)),
        "losing_trades": float(len(losing)),
        "total_fees": total_fees,
    }
