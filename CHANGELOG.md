# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### Phase 6: Backtesting Engine (v0.6.0)
- **BacktestService** — self-contained simulation engine that feeds historical OHLCV data through `TechnicalAnalyzer → StrategyRunner → RiskPipeline` (the same pipeline as live trading); guarantees zero look-ahead bias by only exposing candles `[0..i]` at step `i`
- **Simulated fills** — MARKET orders fill at next-candle open ± configurable slippage; fees deducted from portfolio balance on every fill; stop-losses fill at `stop_loss_price` with no additional slippage
- **Performance metrics** — total return %, Sharpe ratio (daily equity returns, risk-free rate = 0, annualized `sqrt(365)`), max drawdown %, win rate %, profit factor, trade count, and total fees
- **`BacktestService.compare()`** — runs multiple pre-configured services over the same candle set and returns results sorted descending by Sharpe ratio
- **Pydantic result models** (`src/trading_crew/models/backtest.py`) — `BacktestConfig` (with `Field` validators), `BacktestTrade` (frozen), `EquityPoint` (frozen), `BacktestResult` with `summary()`, `to_json()`, and `to_csv()` methods
- **`DatabaseService.get_ohlcv_range()`** — new date-range query for OHLCV data (replaces `limit=N` workaround for historical backtests)
- **`ExchangeService.fetch_ohlcv_range()`** — paginated API fetcher that iterates in forward-time batches of `batch_size=500` to retrieve arbitrarily long date ranges without hitting CCXT per-request caps
- **`scripts/backtest_runner.py`** — standalone CLI with `--symbol`, `--exchange`, `--timeframe`, `--from-date`, `--to-date`, `--output`, `--fetch`, `--data-only`, `--compare`, `--slippage`, `--fee-rate`, `--initial-balance`
- **`make backtest-run`** and **`make backtest-data`** Makefile targets for one-command backtesting and data prep
- **27 new unit tests** in `tests/backtest/test_backtest_service.py` covering core backtest run, fill simulation, stop-loss trigger, no-look-ahead guarantee, metric calculations, Sharpe edge cases, strategy comparison, JSON/CSV export, and empty/flat candle scenarios
- Version bumped to `v0.6.0`

#### Phase 5: Flow Orchestrator (v0.5.0)
- **TradingFlow** — `CrewAI Flow[CycleState]` that replaces the inline while-loop body in `main.py` with typed routing, event hooks, and cycle persistence
- **Routing logic** — `_route_after_market` (halt / skip_strategy / strategy), `_route_after_strategy` (skip_execution / execution), `_route_after_execution` (post_cycle); all routing conditions explicitly specified including budget degrade, market data gate, and interval scheduling
- **Event hooks** — `_on_order_filled` (saves PnL snapshot, re-checks circuit breaker), `_on_circuit_breaker_activated` (persists portfolio, sends critical alert), `_on_stop_loss_triggered` (submits immediate MARKET SELL)
- **Stop-loss monitoring** — `_check_stop_losses()` called every cycle from `post_cycle_hooks`; falls back to `cached_analyses` from the previous market run when market phase is skipped
- **Cross-cycle market analysis cache** — `last_market_analyses` maintained in `main.py` and passed to each `TradingFlow` instance as `cached_analyses` for stop-loss price fallback
- **Hard-stop deterministic poll** — when `HARD_STOP` degrade is active and `non_llm_monitor_on_hard_stop=True`, open orders are still polled even when execution is otherwise skipped
- **Portfolio rollback on skip/failure** — `_portfolio_snapshot` taken before tentative reservations; restored in `post_cycle_hooks` when execution is skipped; also restored in `strategy_phase` on exception (new exception guard)
- **CycleRecord** ORM model (`cycle_history` table) — one row per cycle with signal counts, order counts, portfolio balance, realized P&L, circuit breaker state, and error list; `cycle_number` has a unique index, `timestamp` has a regular index
- **`save_cycle_summary()`** in `DatabaseService` — upserts on `cycle_number` collision (safe on restart); reads `state.circuit_breaker_tripped` for accurate CB tracking
- **`circuit_breaker_tripped: bool`** field added to `CycleState`; set to `True` by `circuit_breaker_halt()`; written to `CycleRecord` for audit trail
- **Stop-loss order counts in cycle state** — `_on_stop_loss_triggered` appends placed/filled/failed orders from the emergency SELL to `state.orders` / `state.filled_orders` / `state.failed_orders` so `CycleRecord` totals are accurate
- **`save_cycle_history`** and **`stop_loss_monitoring_enabled`** settings (both default `True`)
- Alembic migration `fd3e40da0c31` — creates `cycle_history` table
- 32 new unit tests in `tests/unit/test_trading_flow.py` covering all routing paths, budget degrade integration, market data gate, portfolio rollback, event hooks, stop-loss monitoring, position price updates, and cycle persistence

#### Phase 4: Execution Crew (v0.4.0)
- **ExecutionService** — deterministic order placement and lifecycle management pipeline
- **Order lifecycle** — full status tracking: PENDING → OPEN → PARTIALLY_FILLED → FILLED / CANCELLED / REJECTED
- **`_reconcile_fill()`** — "undo-then-apply" pattern replaces tentative Phase 3 portfolio reservations with actual fill data; eliminates double-counting of BUY and SELL paths
- **`_reconcile_incremental_fill()`** — tentative-aware partial fill handling; position remains at full tentative amount during partial fills; only balance is adjusted for price deviation and fees
- **Order precision normalization** — integrates CCXT `amount_to_precision` / `price_to_precision` before placement
- **MARKET BUY validation** — fetches real-time ticker ask price to estimate cost and perform balance check before placement (prevents underfunded orders)
- **`finalize_pending_order()`** in `DatabaseService` — promotes PENDING placeholder records to the real exchange-assigned ID after successful placement; eliminates orphaned PENDING records
- **Stale order cancellation** — configurable timeouts for fully-open orders (`STALE_ORDER_CANCEL_MINUTES`) and partially-filled orders (`STALE_PARTIAL_FILL_CANCEL_MINUTES`)
- **Dead-letter queue** — failed order requests are persisted to `failed_orders` table and exposed via `GetFailedOrdersTool`
- **`SavePortfolioTool`** and **`GetFailedOrdersTool`** — new CrewAI tools for portfolio persistence and dead-letter review
- **`PortfolioRecord`** snapshots — portfolio state saved after each execution cycle with a 10-row retention policy
- **`OrderRecordLike` Protocol** — structural typing for order records enabling duck-typed method signatures without `isinstance` checks
- **`_DEFAULT_FEE_RATE`** constant — `0.001` fee rate extracted to a named constant used by `_reconcile_incremental_fill` and `_build_order_from_record`
- **`ExecutionPipelineMode`** setting (crewai/deterministic/hybrid)
- Alembic migration `d47f90acdc5b` — creates `failed_orders` and `portfolio_snapshots` tables
- 45 new unit tests covering order placement, reconciliation math, stale cancellation, dead-letter queue, precision normalization, and portfolio persistence

#### Phase 3: Strategy Crew
- **StrategyRunner** service — deterministic strategy execution engine with individual and ensemble (weighted voting) modes
- **RiskPipeline** service — full risk validation pipeline: confidence filter, circuit breaker, position sizing, stop-loss (fixed % or ATR-based), portfolio exposure limits, and concentration limits
- **CompositeStrategy** — ensemble strategy that aggregates signals from multiple child strategies via configurable agreement threshold
- **RunStrategiesTool** — CrewAI tool wrapping StrategyRunner for the Strategist agent
- **EvaluateRiskTool** — CrewAI tool wrapping RiskPipeline for the Risk Manager agent
- `StrategyPipelineMode` setting (crewai/deterministic/hybrid)
- Configurable stop-loss method (`STOP_LOSS_METHOD`: fixed/atr)
- Ensemble mode settings (`ENSEMBLE_ENABLED`, `ENSEMBLE_AGREEMENT_THRESHOLD`)
- Initial portfolio balance setting (`INITIAL_BALANCE_QUOTE`)
- `CycleState.order_requests` field for risk-approved order requests
- 36 new unit tests for StrategyRunner, RiskPipeline, and CompositeStrategy
- Strategist and Risk Manager agents now receive deterministic tools

#### Phase 2: Market Intelligence
- Deterministic market intelligence pipeline (fetch → analyze → store)
- TechnicalAnalyzer with EMA, RSI, Bollinger Bands, MACD, ATR, and regime classification
- MarketIntelligenceService for coordinated multi-symbol analysis
- Optional sentiment enrichment (Fear & Greed Index)
- Configurable market regime thresholds
- Cost contention scheduling with daily token budget guards
- `MarketPipelineMode` setting (crewai/deterministic/hybrid)
- `MarketMetadata` typed model for structured analysis metadata
- `CycleState` DTO for inter-crew data handoff

#### Phase 1: Foundation
- Project scaffolding with pyproject.toml, Makefile, and uv support
- Apache 2.0 license and financial disclaimer
- Open-source community files (CONTRIBUTING, CODE_OF_CONDUCT, ARCHITECTURE)
- GitHub Actions CI pipeline, issue templates, and PR template
- Pydantic data models for market, signals, orders, portfolio, and risk
- Configuration system using Pydantic Settings with .env and YAML support
- SQLAlchemy ORM models and Alembic migration setup
- CCXT-based multi-exchange service facade
- CrewAI agent, crew, and tool scaffolding
- Paper trading as the default mode
- Example configurations for Binance and NovaDAX

### Fixed

#### Phase 6
- **`entry_bar` always 0 on every `BacktestTrade`** — `_evaluate_signal` now receives the current candle index and stores it in `_PendingOrder.bar`; an `entry_bars: dict[str, int]` local dict threads the actual fill bar through `_fill_at_open`, `_check_stop_losses`, `_close_position`, and the end-of-data force-close loop so every `BacktestTrade.entry_bar` reflects the true fill bar index
- **Sharpe ratio annualized as daily regardless of timeframe** — added `_periods_per_year(timeframe)` static method; `_compute_metrics` now accepts a `timeframe` argument and annualizes using `sqrt(periods_per_year)` (e.g. `sqrt(8760)` for `1h`, `sqrt(365)` for `1d`) instead of always using `sqrt(365)`
- **BUY silently overwrites an existing open position** — `_fill_at_open` now skips a BUY order when `order.symbol in portfolio.positions`, preventing entry price, amount, and stop-loss from being lost to a second fill
- **Unused `completed_trades` parameter on `_check_stop_losses`** — parameter removed; SL trades are already returned to the caller for appending
- **E402 lint errors in `scripts/backtest_runner.py`** — all `trading_crew` imports moved inside `main()` so they are resolved after the `sys.path.insert`; avoids module-level import-order violations

#### Phase 5
- **Strategy phase reservation leak** — `strategy_phase()` now wraps the deterministic pipeline in `try/except`; any exception after the snapshot is taken triggers an immediate rollback before re-raising, preventing tentative reservations from persisting into the next cycle

#### Phase 4
- **Tentative reservation double-counting** — `_reconcile_fill()` now uses an "undo-then-apply" pattern for both BUY and SELL paths, correctly replacing Phase 3's tentative portfolio state rather than additively stacking on top of it
- **Orphaned PENDING records** — `finalize_pending_order()` replaces the no-op `model_copy(update={"id": order.id})` that was silently leaving PENDING records unlinked after exchange placement
- **MARKET BUY validation bypass** — MARKET orders with `price=None` previously bypassed balance checks; fix fetches the ticker ask price for cost estimation before placement
- **Portfolio snapshot accumulation** — `save_portfolio()` now prunes rows older than the 10-row retention window on every save
