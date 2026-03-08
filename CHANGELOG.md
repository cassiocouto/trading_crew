# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Full simulation backtest** — new `SimulationRunner` runs the real `TradingFlow` per historical candle against a `SimulatedExchangeService` and in-memory SQLite database; produces the same `BacktestResult` format as the legacy `BacktestService`; includes circuit-breaker halting, break-even sell guards, anti-averaging-down, and all DB-dependent guards
- **`SimulatedExchangeService`** (`services/simulated_exchange.py`) — drop-in mock of `ExchangeService` implementing all 12 async methods + 2 properties; replays preloaded candles, simulates immediate order fills at close +/- slippage; single-symbol scope with `ValueError` on unknown symbols
- **`candle_loader.load_candles_csv()`** (`services/candle_loader.py`) — parses Binance kline CSV files (headerless or with header) into `list[OHLCV]`; supports `start`/`end` date filtering, `max_bars` truncation, and OHLCV-correct resampling to larger timeframes (e.g. 1m → 1h)
- **`--simulation` CLI flag** on `scripts/backtest_runner.py` — routes to `SimulationRunner` instead of legacy `BacktestService`
- **`--candles-file`** CLI flag — load candles from a local CSV file (Binance kline format) instead of fetching from the exchange; `--from-date`/`--to-date` become optional when using this flag
- **`--resample`** CLI flag — aggregate loaded candles to a larger timeframe (e.g. `--resample 1h`)
- **`--max-bars`** CLI flag (default: 50,000) — safety valve to prevent accidental multi-million bar runs
- **`simulation_mode` field** on `BacktestConfig`, `BacktestRunRequest` API schema, and backtest router — when true, API uses `SimulationRunner`
- **Full Simulation toggle** on the dashboard backtest page — checkbox next to the advisory mode selector
- **39 new unit tests** — `test_simulated_exchange.py` (17 tests), `test_candle_loader.py` (14 tests), `test_simulation_runner.py` (7 tests) covering method coverage, CSV parsing, resampling, circuit-breaker halting, and equity curve correctness

### Fixed

- **SELL orders always failing validation** — `reserve_phase` tentatively removed positions before `execution_phase` could validate them; added `sell_validation_portfolio` parameter to `ExecutionService._validate_order()` scoped to SELL position checks only (BUY balance checks still use the post-reserve portfolio to prevent over-spending)
- **Duplicate SELL orders per symbol** — multiple strategies could each emit a full-position SELL for the same symbol; added `_dedup_sell_orders()` at the top of `reserve_phase` (the single convergence point for advisory + non-advisory paths) that merges SELLs per symbol to max(amounts) capped at position size
- **Stop-loss sells failing with "no position to sell"** — removed tentative portfolio reservation from `_on_stop_loss_triggered`; the position now stays in the portfolio until execution fills the order, and is preserved unchanged if execution fails (also resolves the stop-loss rollback issue from the prior review)
- **`_build_trades` undercounting completed round-trips** — replaced single-buy `dict[str, OrderRecord]` with FIFO lot matching using `deque[_BuyLot]` per symbol; supports partial fills (split buys when sell amount < buy amount, residual stays on queue)
- **15 new tests** for sell validation, SELL dedup, stop-loss without tentative reservation, and FIFO lot matching with partial fills

## [0.10.0] — 2026-03-04

### Added

- **Anti-averaging-down guard** — new `ANTI_AVERAGING_DOWN` setting (default `true`); rejects BUY signals whose proposed entry price is at or below the existing position's stop-loss price; guard resets automatically when the position fully closes (logs + optional Telegram notification)
- **Break-even sell guard** — new `SELL_GUARD_MODE` setting (`break_even` by default); holds signal-driven sell orders until the proposed price clears the most recently filled BUY lot's break-even; stop-loss exits bypass the guard by design
- **`break_even_price` DB column** — nullable `Float` added to `orders` table via Alembic migration; computed once in `ExecutionService._compute_break_even()` when a BUY fill is confirmed and stored via `save_order()`
- **`get_break_even_prices(symbols)` on `DatabaseService`** — single batched query returning the most recent filled BUY break-even per symbol; called in `TradingFlow.strategy_phase()` so `RiskPipeline` stays I/O-free
- **`min_profit_margin_pct` field on `RiskParams`** (default `0.0`) — adds an optional profit margin above break-even before a sell is approved; configurable via `RISK__MIN_PROFIT_MARGIN_PCT`
- **`SellGuard` ABC** in `risk/sell_guard.py` — pluggable interface; ships with `AllowAllSellGuard` (pass-through) and `BreakEvenSellGuard` (LIFO break-even check)
- **`anti_averaging_down_enabled` flag on `ExecutionService`** — gates the guard-reset Telegram notification so it only fires when the guard is actually active
- Version bumped to `v0.10.0`

### Changed

- `RiskPipeline.__init__` gains two optional params: `anti_averaging_down: bool = False` and `sell_guard: SellGuard | None = None`
- `RiskPipeline.evaluate()` gains optional `break_even_prices: dict[str, float | None] | None = None` parameter (passed from `TradingFlow`)
- `BacktestService` now explicitly passes `anti_averaging_down=False` and `sell_guard=AllowAllSellGuard()` to keep backtest behaviour unaffected
- `ExecutionService.__init__` gains optional `anti_averaging_down_enabled: bool = False` parameter

---

## [0.9.0] — 2026-03-04

### Added

- **Live wallet balance seeding** — in live mode, `portfolio.balance_quote` is now seeded from `exchange_service.fetch_balance()` at startup instead of `INITIAL_BALANCE_QUOTE`; startup aborts with a clear error if the circuit breaker is open or the balance is zero
- **Pre-cycle wallet sync** — `_sync_balance_if_due()` helper runs at the top of each trading cycle (live mode only) to re-sync `portfolio.balance_quote` from the exchange; catches external deposits and withdrawals without restarting the bot
- **`BALANCE_SYNC_INTERVAL_SECONDS` setting** (default `300`) — how often the wallet sync runs; set to `0` to disable
- **`BALANCE_DRIFT_ALERT_THRESHOLD_PCT` setting** (default `1.0`) — sends a Telegram notification when the synced balance drifts by this percentage or more
- **`quote_currency` computed property** on `Settings` — derived from the first configured symbol (e.g. `BTC/USDT` → `USDT`); used throughout balance seeding and sync
- Version bumped to `v0.9.0`

### Changed

- `INITIAL_BALANCE_QUOTE` now applies **only to paper trading**; it is ignored in live mode

---

## [0.8.0] — 2026-03-04

### Added

#### Phase 8: Hardening and Optimization (v0.8.0)

- **Async CCXT (`ccxt.async_support`)** — `ExchangeService` fully converted to async; all public methods are now `async def` using `await exchange.<method>()` directly; `ExchangeTool` exposes `_run()` (sync wrapper via `asyncio.run`) and `_arun()` (native async) for CrewAI tool compatibility; `ExecutionService`, `MarketIntelligenceService`, `TradingFlow` exec-phase methods, and `scripts/backtest_runner.py` updated accordingly
- **API-level exchange rate-limit circuit breaker** in `ExchangeService` — tracks consecutive `ccxt.RateLimitExceeded` failures; once `exchange_rate_limit_threshold` (default 5) is reached, all calls are blocked for `exchange_rate_limit_cooldown_seconds` (default 60) and `ExchangeCircuitBreakerError` is raised; resets on first success; layered above `_retry()` exhaustion
- **Async `_retry()` instance method** — accepts a `coro_factory: Callable[[], Awaitable[T]]` to avoid coroutine reuse errors; uses `await asyncio.sleep()` for non-blocking backoff; callable from `_call()` which also manages circuit-breaker state
- **`fetch_tickers_parallel()`** — batches multiple ticker fetches in a single `asyncio.gather()` for efficient multi-symbol market scans
- **Cross-platform graceful shutdown** — `main.py` uses `asyncio.Event` + `loop.call_soon_threadsafe` instead of a bare flag; `SIGINT`/`SIGTERM` handlers set the event from the signal thread; `asyncio.run(main_async())` wraps the trading loop; `await exchange_service.close()` called on shutdown
- **CrewAI Flow async compatibility** — all `@router` and `@listen` methods in `TradingFlow` converted to `async def`; router method names without leading `_` (e.g. `route_after_market`) to comply with CrewAI 1.9+ `_methods` registry requirements; `await flow.akickoff()` used in the trading loop
- **DB connection pooling** — `get_engine()` accepts `pool_size`, `max_overflow`, `pool_timeout`; reads from new `Settings` fields (`database_pool_size`, `database_max_overflow`, `database_pool_timeout`); pooling parameters applied only for non-SQLite URLs (SQLite uses `StaticPool` / default pool); `DatabaseService.__init__` now accepts either a URL string or an `Engine` object directly
- **`StateProxy` unwrapping in `DatabaseService.save_cycle_summary()`** — `crewai.flow.flow.StateProxy` wrapper is transparently unwrapped via `_proxy_state` attribute so persistence works correctly with `akickoff()`
- **Integration tests** (`tests/integration/`) — `test_full_cycle.py`: two async tests using in-memory SQLite (`StaticPool`) and a fully mocked `AsyncMock` exchange; verifies `CycleRecord` + `PortfolioRecord` persistence and no-exception completion; `test_backtest_regression.py`: two tests guarding `EMACrossoverStrategy` backtest metrics (trade count, Sharpe ratio, win rate) against regressions on deterministic bullish fixtures
- **`integration-tests` CI job** in `.github/workflows/ci.yml` — runs after the `test` job (`needs: test`); executes `pytest -m integration`
- **Docker support** — multi-stage `Dockerfile` (builder + runtime, non-root `trader` user, `/app/data` volume); `dashboard/Dockerfile` (deps → builder → runtime with `output:standalone`); `docker-compose.yml` (api + dashboard services, SQLite bind-mount, commented-out PostgreSQL alternative); `.dockerignore`
- **`output: "standalone"` in `dashboard/next.config.ts`** — enables minimal Docker runtime bundle without full `node_modules`
- **Makefile targets** — `docker-build`, `docker-up`, `docker-down`
- **`.devcontainer/devcontainer.json`** — dev container with Python 3.12 + uv + Node 20; forwards ports 8000 and 3000; installs Ruff, mypy, Tailwind, ESLint extensions
- **`examples/.env.paper`** and **`examples/.env.live`** — annotated environment templates for paper-trading and live-trading setups
- **`release.yml` GitHub Actions workflow** — triggered on `v*.*.*` tags; runs tests, publishes to PyPI via Trusted Publishers (OIDC), pushes Docker images to GHCR, creates a GitHub Release with auto-generated notes
- Version bumped to `v0.8.0`

### Changed

- `TradingFlow` router methods renamed from `_route_after_*` to `route_after_*` (no leading underscore) to comply with CrewAI 1.9+ method-registry requirements
- `DatabaseService` type signature for `__init__` parameter broadened to accept `Engine | str | None`

---

### Added

#### Phase 7: Dashboard and Observability (v0.7.0)
- **FastAPI dashboard backend** (`src/trading_crew/api/`) — read-only REST API and WebSocket endpoint running as a separate process that shares the same SQLite database via WAL mode; no modifications to the trading loop required
- **7 REST API routers** — `portfolio` (snapshot + history), `orders` (with filtering), `signals` (with strategy filter), `cycles`, `system`, `agents`, and `backtest` endpoints
- **WebSocket live updates** (`/ws/events`) — server-side DB polling every 3 s detects new rows via ID watermarks and broadcasts `cycle_complete`, `order_filled`, `signal_generated`, and `circuit_breaker` events to all connected clients; React Query cache is invalidated on each event
- **Agent observability** (`GET /api/agents/`) — per-agent pipeline mode, last activity timestamp, estimated token usage, and active status; derived from settings and the latest `CycleRecord` (no cross-process CrewAI tracing required)
- **Strategy performance stats** (`GET /api/signals/strategy-stats`) — two separate `GROUP BY` queries on `TradeSignalRecord` and `OrderRecord` merged in Python by `strategy_name`, providing total signals, buy/sell split, avg confidence, orders placed, and fill rate
- **Next.js dashboard frontend** (`dashboard/`) — TypeScript, Tailwind CSS, Recharts, React Query; 6 pages: Overview, Orders, Signals, History, Agents, Backtest; `useWebSocket` hook with auto-reconnect; sidebar navigation and dark-safe styling
- **SQLite WAL concurrency** — FastAPI engine configured with `PRAGMA journal_mode=WAL` and `busy_timeout=5000`; backtest endpoint is purely read-only to eliminate write contention
- **Non-blocking backtest endpoint** — `POST /api/backtest/run` is a synchronous `def` handler so FastAPI automatically offloads it to a threadpool executor, keeping the async event loop free
- **`TelegramNotifyLevel` StrEnum** in `settings.py` with values `ALL`, `TRADES_ONLY`, `CRITICAL_ONLY`; `telegram_notify_level` setting defaults to `TRADES_ONLY`
- **Structured Telegram alert methods** — `notify_order_filled`, `notify_stop_loss_triggered`, `notify_circuit_breaker_activated`, `notify_cycle_summary`; each respects the configured notify level
- **`dashboard_*` settings** — `dashboard_enabled`, `dashboard_host`, `dashboard_port`, `dashboard_cors_origins`, `dashboard_api_key`, `dashboard_ws_poll_interval_seconds`; optional API key authentication middleware
- **`DatabaseService.get_latest_cycle()`** — returns the most recent `CycleRecord` (expunged from session so callers can read attributes after session close)
- **`scripts/dashboard.py`** — uvicorn launcher with `--host`, `--port`, `--reload`, `--log-level` CLI flags
- **`make dashboard-api`**, **`make dashboard-ui`**, **`make dashboard-install`** Makefile targets
- **36 new unit tests** in `tests/unit/test_dashboard_api.py` — `TestPortfolioEndpoints`, `TestOrderEndpoints`, `TestSignalEndpoints`, `TestCycleEndpoints`, `TestSystemStatus`, `TestAgentsEndpoint`, `TestBacktestEndpoint`, `TestAuth`, `TestNotificationService`, `TestWebSocket`; all using FastAPI `TestClient` with in-memory SQLite via `StaticPool`
- Version bumped to `v0.7.0`

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
