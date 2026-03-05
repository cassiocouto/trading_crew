"""Backtesting engine for Phase 6.

Feeds historical OHLCV data through the same TechnicalAnalyzer -> StrategyRunner
-> RiskPipeline used in live trading, simulates MARKET fills at next-candle open
with configurable slippage and fees, and computes standard performance metrics.

Design guarantees:
  - Zero look-ahead bias: at candle i, only candles[0..i] are visible.
  - Simulated orders fill at candle[i+1].open ± slippage.
  - Stop-losses are checked against candle[i].low (intra-bar breach).
  - Pure in-memory: no DB reads/writes, no Alembic migrations needed.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from trading_crew.models.backtest import (
    BacktestConfig,
    BacktestResult,
    BacktestTrade,
    EquityPoint,
)
from trading_crew.models.portfolio import Portfolio, Position
from trading_crew.models.signal import SignalType
from trading_crew.services.technical_analyzer import TechnicalAnalyzer

if TYPE_CHECKING:
    from datetime import datetime

    from trading_crew.models.market import OHLCV, MarketAnalysis
    from trading_crew.models.risk import RiskParams
    from trading_crew.models.signal import TradeSignal
    from trading_crew.services.strategy_runner import StrategyRunner

logger = logging.getLogger(__name__)

# Seconds per timeframe string — used to assign candle timestamps when missing.
_TIMEFRAME_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


class _PendingOrder:
    """Internal queue entry for a simulated order awaiting next-bar fill."""

    __slots__ = ("amount", "bar", "side", "stop_loss_price", "strategy_name", "symbol", "ts")

    def __init__(
        self,
        symbol: str,
        side: str,
        amount: float,
        stop_loss_price: float | None,
        strategy_name: str,
        bar: int,
        ts: datetime,
    ) -> None:
        self.symbol = symbol
        self.side = side
        self.amount = amount
        self.stop_loss_price = stop_loss_price
        self.strategy_name = strategy_name
        self.bar = bar
        self.ts = ts


class BacktestService:
    """Runs backtests over a list of OHLCV candles.

    Args:
        strategy_runner: Pre-configured StrategyRunner with one or more strategies.
        risk_params: Risk configuration (position sizing, stop-loss, etc.).
        config: Backtest simulation parameters (fees, slippage, window size).
        stop_loss_method: "fixed" or "atr" — passed through to the RiskPipeline.
        atr_stop_multiplier: ATR multiplier for ATR-based stop-losses.
    """

    def __init__(
        self,
        strategy_runner: StrategyRunner,
        risk_params: RiskParams,
        config: BacktestConfig | None = None,
        stop_loss_method: str = "fixed",
        atr_stop_multiplier: float = 2.0,
    ) -> None:
        self._runner = strategy_runner
        self._risk_params = risk_params
        self._config = config or BacktestConfig()
        self._stop_loss_method = stop_loss_method
        self._atr_stop_multiplier = atr_stop_multiplier
        self._analyzer = TechnicalAnalyzer()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        symbol: str,
        exchange: str,
        candles: list[OHLCV],
        timeframe: str = "1h",
    ) -> BacktestResult:
        """Run a full backtest over the provided candle list.

        Args:
            symbol: Trading pair (e.g. "BTC/USDT").
            exchange: Exchange identifier.
            candles: Historical OHLCV data, oldest first.
            timeframe: Candle period string — used only for labelling.

        Returns:
            BacktestResult with trades, equity curve, and aggregate metrics.

        Raises:
            ValueError: If the candle list is shorter than min_candles_for_analysis.
        """
        cfg = self._config
        if len(candles) < cfg.min_candles_for_analysis:
            raise ValueError(
                f"Not enough candles: need {cfg.min_candles_for_analysis}, got {len(candles)}"
            )

        portfolio = Portfolio(
            balance_quote=cfg.initial_balance,
            peak_balance=cfg.initial_balance,
        )

        pending_orders: list[_PendingOrder] = []
        completed_trades: list[BacktestTrade] = []
        equity_curve: list[EquityPoint] = []
        peak_equity = cfg.initial_balance
        # Maps symbol -> fill bar index so entry_bar is accurate on every BacktestTrade.
        entry_bars: dict[str, int] = {}

        for i, candle in enumerate(candles):
            # ---- Fill any pending orders at this candle's open ----
            if pending_orders:
                fills = self._fill_at_open(candle, pending_orders, portfolio, i, entry_bars)
                completed_trades.extend(fills)
                pending_orders.clear()

            # ---- Check stop-losses against intra-bar low ----
            sl_fills = self._check_stop_losses(candle, portfolio, i, entry_bars)
            completed_trades.extend(sl_fills)

            # ---- Skip analysis until warm-up window is ready ----
            if i < cfg.min_candles_for_analysis - 1:
                self._record_equity(candle, portfolio, peak_equity, equity_curve)
                peak_equity = max(peak_equity, portfolio.total_balance)
                continue

            # ---- Technical analysis on rolling window ----
            window_start = max(0, i + 1 - cfg.candle_window_size)
            window = candles[window_start : i + 1]
            try:
                analysis = self._analyzer.analyze_from_candles(symbol, exchange, window)
            except Exception:
                logger.debug("Analysis failed at bar %d, skipping", i)
                self._record_equity(candle, portfolio, peak_equity, equity_curve)
                peak_equity = max(peak_equity, portfolio.total_balance)
                continue

            # ---- Update position prices for accurate unrealized P&L ----
            for pos in portfolio.positions.values():
                pos.current_price = candle.close

            # ---- Strategy signals ----
            signals = self._runner.evaluate({symbol: analysis})

            # ---- Risk pipeline + queue orders ----
            for signal in signals:
                order = self._evaluate_signal(signal, portfolio, analysis, bar=i)
                if order is not None:
                    pending_orders.append(order)

            # ---- Record equity snapshot ----
            self._record_equity(candle, portfolio, peak_equity, equity_curve)
            peak_equity = max(peak_equity, portfolio.total_balance)

        # ---- Force-close any remaining open positions at last candle close ----
        if candles:
            last_candle = candles[-1]
            last_bar = len(candles) - 1
            for sym, pos in list(portfolio.positions.items()):
                trade = self._close_position(
                    sym,
                    pos,
                    exit_price=last_candle.close,
                    exit_bar=last_bar,
                    exit_ts=last_candle.timestamp,
                    exit_reason="end_of_data",
                    portfolio=portfolio,
                    entry_bar=entry_bars.pop(sym, 0),
                )
                completed_trades.append(trade)

        metrics = self._compute_metrics(
            completed_trades, equity_curve, cfg.initial_balance, timeframe
        )

        return BacktestResult(
            symbol=symbol,
            exchange=exchange,
            timeframe=timeframe,
            strategy_names=self._runner.strategy_names,
            start_date=candles[0].timestamp,
            end_date=candles[-1].timestamp,
            initial_balance=cfg.initial_balance,
            final_balance=portfolio.total_balance,
            total_return_pct=metrics["total_return_pct"],
            sharpe_ratio=metrics["sharpe_ratio"],
            max_drawdown_pct=metrics["max_drawdown_pct"],
            win_rate_pct=metrics["win_rate_pct"],
            profit_factor=metrics["profit_factor"],
            total_trades=len(completed_trades),
            winning_trades=metrics["winning_trades"],
            losing_trades=metrics["losing_trades"],
            total_fees=metrics["total_fees"],
            trades=completed_trades,
            equity_curve=equity_curve,
        )

    @staticmethod
    def compare(
        services: list[BacktestService],
        symbol: str,
        exchange: str,
        candles: list[OHLCV],
        timeframe: str = "1h",
    ) -> list[BacktestResult]:
        """Run multiple pre-configured services over the same candle set.

        Args:
            services: List of BacktestService instances, each with different strategies/params.
            symbol: Trading pair.
            exchange: Exchange identifier.
            candles: Shared historical OHLCV data.
            timeframe: Candle period label.

        Returns:
            List of BacktestResult sorted descending by Sharpe ratio (NaN last).
        """
        results: list[BacktestResult] = []
        for svc in services:
            try:
                result = svc.run(symbol, exchange, candles, timeframe)
                results.append(result)
            except Exception:
                logger.exception("BacktestService.compare: service failed")

        def _sort_key(r: BacktestResult) -> float:
            return r.sharpe_ratio if not math.isnan(r.sharpe_ratio) else float("-inf")

        return sorted(results, key=_sort_key, reverse=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evaluate_signal(
        self,
        signal: TradeSignal,
        portfolio: Portfolio,
        analysis: MarketAnalysis,
        bar: int = 0,
    ) -> _PendingOrder | None:
        """Run a signal through the risk pipeline and return a queued order."""
        from trading_crew.risk.circuit_breaker import CircuitBreaker
        from trading_crew.risk.sell_guard import AllowAllSellGuard
        from trading_crew.services.risk_pipeline import RiskPipeline

        cb = CircuitBreaker(self._risk_params)
        pipeline = RiskPipeline(
            self._risk_params,
            cb,
            stop_loss_method=self._stop_loss_method,
            atr_stop_multiplier=self._atr_stop_multiplier,
            anti_averaging_down=False,  # guards always off in backtest
            sell_guard=AllowAllSellGuard(),  # guards always off in backtest
        )
        result = pipeline.evaluate(signal, portfolio, analysis)
        if not result.is_approved or result.approved_amount <= 0:
            return None

        return _PendingOrder(
            symbol=signal.symbol,
            side="buy" if signal.signal_type == SignalType.BUY else "sell",
            amount=result.approved_amount,
            stop_loss_price=result.stop_loss_price,
            strategy_name=signal.strategy_name,
            bar=bar,
            ts=signal.timestamp,
        )

    def _fill_at_open(
        self,
        candle: OHLCV,
        pending_orders: list[_PendingOrder],
        portfolio: Portfolio,
        bar: int,
        entry_bars: dict[str, int],
    ) -> list[BacktestTrade]:
        """Fill queued orders at next candle open ± slippage."""
        cfg = self._config
        trades: list[BacktestTrade] = []

        for order in pending_orders:
            if order.side == "buy":
                # Skip if a position is already open for this symbol to avoid overwriting
                # entry price, amount, and stop-loss with a second fill.
                if order.symbol in portfolio.positions:
                    logger.debug(
                        "Skipping BUY: position already open for %s at bar %d",
                        order.symbol,
                        bar,
                    )
                    continue

                fill_price = candle.open * (1 + cfg.slippage_pct)
                cost = fill_price * order.amount
                fee = cost * cfg.fee_rate

                if portfolio.balance_quote < cost + fee:
                    # Reduce amount to what's affordable
                    affordable = portfolio.balance_quote / (fill_price * (1 + cfg.fee_rate))
                    if affordable <= 0:
                        logger.debug("Skipping BUY: insufficient balance at bar %d", bar)
                        continue
                    order.amount = affordable
                    cost = fill_price * order.amount
                    fee = cost * cfg.fee_rate

                portfolio.balance_quote -= cost + fee
                portfolio.total_fees += fee

                position = Position(
                    symbol=order.symbol,
                    exchange="backtest",
                    side="long",
                    entry_price=fill_price,
                    amount=order.amount,
                    current_price=fill_price,
                    stop_loss_price=order.stop_loss_price,
                    opened_at=candle.timestamp,
                    strategy_name=order.strategy_name,
                )
                portfolio.positions[order.symbol] = position
                # Record fill bar as the true entry bar (one candle after signal bar).
                entry_bars[order.symbol] = bar
                portfolio.update_peak()

                logger.debug(
                    "BUY fill bar=%d price=%.4f amount=%.6f fee=%.4f",
                    bar,
                    fill_price,
                    order.amount,
                    fee,
                )

            elif order.side == "sell":
                pos = portfolio.positions.get(order.symbol)
                if pos is None:
                    continue

                fill_price = candle.open * (1 - cfg.slippage_pct)
                proceeds = fill_price * order.amount
                fee = proceeds * cfg.fee_rate
                net_proceeds = proceeds - fee
                entry_cost = pos.entry_price * order.amount
                entry_fee = entry_cost * cfg.fee_rate
                pnl = net_proceeds - entry_cost - entry_fee

                portfolio.balance_quote += net_proceeds
                portfolio.realized_pnl += pnl
                portfolio.total_fees += fee

                if abs(order.amount - pos.amount) < 1e-10:
                    del portfolio.positions[order.symbol]
                    recorded_entry_bar = entry_bars.pop(order.symbol, 0)
                else:
                    pos.amount -= order.amount
                    recorded_entry_bar = entry_bars.get(order.symbol, 0)

                portfolio.update_peak()

                trades.append(
                    BacktestTrade(
                        symbol=order.symbol,
                        side="sell",
                        strategy_name=order.strategy_name,
                        entry_bar=recorded_entry_bar,
                        exit_bar=bar,
                        entry_price=pos.entry_price,
                        exit_price=fill_price,
                        amount=order.amount,
                        pnl=pnl,
                        fee=fee + entry_fee,
                        exit_reason="sell_signal",
                        opened_at=order.ts,
                        closed_at=candle.timestamp,
                    )
                )

        return trades

    def _check_stop_losses(
        self,
        candle: OHLCV,
        portfolio: Portfolio,
        bar: int,
        entry_bars: dict[str, int],
    ) -> list[BacktestTrade]:
        """Check intra-bar stop-loss breaches and close positions.

        Stop-loss fills use the stop_loss_price itself (no additional slippage)
        to model a realistic limit-stop fill.
        """
        cfg = self._config
        trades: list[BacktestTrade] = []

        for symbol, pos in list(portfolio.positions.items()):
            if pos.stop_loss_price is None:
                continue
            if candle.low > pos.stop_loss_price:
                continue

            exit_price = pos.stop_loss_price
            trade = self._close_position(
                symbol,
                pos,
                exit_price=exit_price,
                exit_bar=bar,
                exit_ts=candle.timestamp,
                exit_reason="stop_loss",
                portfolio=portfolio,
                fee_rate=cfg.fee_rate,
                entry_bar=entry_bars.pop(symbol, 0),
            )
            trades.append(trade)

        return trades

    def _close_position(
        self,
        symbol: str,
        pos: Position,
        exit_price: float,
        exit_bar: int,
        exit_ts: datetime,
        exit_reason: str,
        portfolio: Portfolio,
        fee_rate: float | None = None,
        entry_bar: int = 0,
    ) -> BacktestTrade:
        """Close a position and update the portfolio."""
        if fee_rate is None:
            fee_rate = self._config.fee_rate

        proceeds = exit_price * pos.amount
        fee = proceeds * fee_rate
        net_proceeds = proceeds - fee
        entry_cost = pos.entry_price * pos.amount
        entry_fee = entry_cost * fee_rate
        pnl = net_proceeds - entry_cost - entry_fee

        portfolio.balance_quote += net_proceeds
        portfolio.realized_pnl += pnl
        portfolio.total_fees += fee
        del portfolio.positions[symbol]
        portfolio.update_peak()

        return BacktestTrade(
            symbol=symbol,
            side="sell",
            strategy_name=pos.strategy_name,
            entry_bar=entry_bar,
            exit_bar=exit_bar,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            amount=pos.amount,
            pnl=pnl,
            fee=fee + entry_fee,
            exit_reason=exit_reason,
            opened_at=pos.opened_at,
            closed_at=exit_ts,
        )

    @staticmethod
    def _record_equity(
        candle: OHLCV,
        portfolio: Portfolio,
        peak_equity: float,
        equity_curve: list[EquityPoint],
    ) -> None:
        """Append a snapshot of current portfolio value to the equity curve."""
        total = portfolio.total_balance
        unrealized = portfolio.total_unrealized_pnl
        drawdown = ((peak_equity - total) / peak_equity * 100) if peak_equity > 0 else 0.0
        equity_curve.append(
            EquityPoint(
                timestamp=candle.timestamp,
                balance=total,
                unrealized_pnl=unrealized,
                drawdown_pct=max(0.0, drawdown),
            )
        )

    @staticmethod
    def _periods_per_year(timeframe: str) -> float:
        """Return the number of candles per year for a given timeframe string.

        Used to compute the correct annualization factor for Sharpe ratio:
          annualization_factor = sqrt(periods_per_year)

        Examples: "1m" → 525,600  "1h" → 8,760  "1d" → 365
        Unknown timeframes fall back to "1h" (8,760).
        """
        seconds = _TIMEFRAME_SECONDS.get(timeframe, _TIMEFRAME_SECONDS["1h"])
        return (365 * 24 * 3600) / seconds

    @staticmethod
    def _compute_metrics(
        trades: list[BacktestTrade],
        equity_curve: list[EquityPoint],
        initial_balance: float,
        timeframe: str = "1h",
    ) -> dict[str, float]:
        """Compute aggregate performance metrics.

        Sharpe ratio:
          - Computed from per-candle equity returns (one data point per bar).
          - Risk-free rate = 0 (standard for crypto).
          - Annualized by sqrt(periods_per_year) where periods_per_year is derived
            from the timeframe string: e.g. sqrt(8760) for 1h, sqrt(365) for 1d.
          - Returns float("nan") when fewer than 2 equity points are available.

        Returns dict with keys: total_return_pct, sharpe_ratio, max_drawdown_pct,
        win_rate_pct, profit_factor, winning_trades, losing_trades, total_fees.
        """
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

        # Sharpe: per-candle returns, annualized by sqrt(periods_per_year).
        # Using _TIMEFRAME_SECONDS directly (module-level constant, no self needed).
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
            "total_return_pct": total_return_pct,
            "sharpe_ratio": sharpe,
            "max_drawdown_pct": max_drawdown_pct,
            "win_rate_pct": win_rate_pct,
            "profit_factor": profit_factor,
            "winning_trades": float(len(winning)),
            "losing_trades": float(len(losing)),
            "total_fees": total_fees,
        }
