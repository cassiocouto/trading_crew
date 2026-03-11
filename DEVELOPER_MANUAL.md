# Trading Crew — Developer Manual

This manual is for developers who want to understand the internals of Trading Crew, extend it with new strategies or tools, contribute to the project, or deploy it in a production environment. If you just want to run the bot, see [USER_MANUAL.md](USER_MANUAL.md) instead.

---

## Table of Contents

1. [Project Philosophy](#1-project-philosophy)
2. [Repository Layout](#2-repository-layout)
3. [Development Setup](#3-development-setup)
4. [How a Trading Cycle Works](#4-how-a-trading-cycle-works)
5. [Adding a Trading Strategy](#5-adding-a-trading-strategy)
6. [Adding a New Indicator](#6-adding-a-new-indicator)
7. [The Agent and Tool System](#7-the-agent-and-tool-system)
8. [Adding a CrewAI Tool](#8-adding-a-crewai-tool)
9. [The Database Layer](#9-the-database-layer)
10. [Adding a Database Migration](#10-adding-a-database-migration)
11. [The API and Dashboard Backend](#11-the-api-and-dashboard-backend)
12. [Testing](#12-testing)
13. [Code Standards](#13-code-standards)
14. [Configuration Internals](#14-configuration-internals)
15. [Docker and Deployment](#15-docker-and-deployment)
16. [CI/CD Pipeline](#16-cicd-pipeline)
17. [Key Extension Points Summary](#17-key-extension-points-summary)

---

## 1. Project Philosophy

Three principles guide every design decision in this codebase:

**Safety first.** Paper trading is the default. Every trade signal goes through a deterministic risk pipeline before any order is placed. The circuit breaker is a hard stop, not a soft warning.

**Separation of concerns.** Each agent does one job. Services contain business logic; tools are thin wrappers that expose services to agents; the flow orchestrates without knowing implementation details.

**Pluggability.** Strategies, exchanges, and notification backends are swappable by design. Adding a new strategy requires creating one file and registering it in one list. The rest of the system adapts automatically.

---

## 2. Repository Layout

```
trading_crew/
├── src/trading_crew/          Main Python package
│   ├── main.py                Entry point — event loop, shutdown handling
│   ├── config/
│   │   ├── settings.py        Pydantic Settings (priority: env > .env > yaml > defaults)
│   │   ├── settings.yaml.example  Version-controlled template for non-secret settings
│   │   ├── settings.yaml      User's local non-secret settings (gitignored)
│   │   ├── runtime_flags.py   Atomic reader/writer for runtime.yaml control flags
│   │   ├── runtime.yaml       Live execution_paused / advisory_paused flags (gitignored)
│   │   ├── agents.yaml        CrewAI agent role/goal/backstory definitions
│   │   └── tasks.yaml         CrewAI task definitions
│   ├── models/                Pydantic domain models (pure data, no logic)
│   │   ├── market.py          OHLCV, Ticker, MarketAnalysis
│   │   ├── signal.py          TradeSignal, SignalType, SignalStrength
│   │   ├── order.py           Order, OrderRequest, OrderFill, OrderStatus
│   │   ├── portfolio.py       Portfolio, Position, PnLSnapshot
│   │   ├── risk.py            RiskCheckResult, RiskParams
│   │   └── cycle.py           CycleState (inter-crew data contract)
│   ├── flows/
│   │   └── trading_flow.py    CrewAI Flow — cycle orchestration
│   ├── crews/                 CrewAI Crew builders (wire agents + tasks)
│   │   ├── market_crew.py
│   │   ├── strategy_crew.py
│   │   └── execution_crew.py
│   ├── agents/                One file per agent role
│   │   ├── sentinel.py        Fetches market data
│   │   ├── analyst.py         Computes indicators
│   │   ├── sentiment.py       Optional sentiment enrichment
│   │   ├── strategist.py      Generates trade signals
│   │   ├── risk_manager.py    Validates signals against risk limits
│   │   ├── executor.py        Places orders
│   │   └── monitor.py         Tracks order lifecycle
│   ├── tools/                 CrewAI Tool wrappers
│   │   ├── exchange_tool.py   Tools backed by ExchangeService
│   │   ├── database_tool.py   Tools backed by DatabaseService
│   │   └── notification_tool.py Tools backed by NotificationService
│   ├── strategies/            Pluggable trading strategies
│   │   ├── base.py            BaseStrategy ABC
│   │   ├── ema_crossover.py
│   │   ├── bollinger.py       Fires within proximity_pct of band edge (default 10%)
│   │   ├── rsi_range.py
│   │   ├── macd_crossover.py  MACD histogram direction; fires every non-flat cycle
│   │   └── composite.py       Ensemble voting logic
│   ├── services/              Infrastructure services
│   │   ├── exchange_service.py    Async CCXT wrapper + circuit breaker
│   │   ├── database_service.py    High-level DB operations
│   │   ├── market_intelligence_service.py  Deterministic market pipeline
│   │   ├── strategy_runner.py     Deterministic strategy execution
│   │   ├── risk_pipeline.py       Deterministic risk validation
│   │   ├── execution_service.py   Order placement + polling
│   │   ├── notification_service.py    Telegram + log
│   │   ├── technical_analysis.py  pandas-ta indicator computation
│   │   ├── sentiment_service.py   Optional sentiment enrichment
│   │   ├── backtest_service.py    Legacy fast backtesting engine
│   │   ├── simulated_exchange.py  Mock exchange for full simulation backtest
│   │   ├── simulation_runner.py   Full-fidelity TradingFlow simulation runner
│   │   └── candle_loader.py       CSV candle loader (Binance kline format)
│   ├── risk/
│   │   ├── circuit_breaker.py     Portfolio drawdown circuit breaker
│   │   ├── position_sizer.py      Kelly-inspired position sizing
│   │   ├── stop_loss.py           Fixed and ATR stop-loss calculators
│   │   ├── portfolio_limits.py    Exposure and concentration checks
│   │   └── sell_guard.py          SellGuard ABC + BreakEvenSellGuard + AllowAllSellGuard
│   ├── db/
│   │   ├── models.py              SQLAlchemy ORM models
│   │   ├── session.py             Engine factory, session context manager
│   │   └── migrations/            Alembic migration scripts
│   └── api/
│       ├── app.py                 FastAPI application factory
│       ├── schemas.py             Pydantic response schemas
│       ├── deps.py                FastAPI dependency injection
│       ├── websocket.py           WebSocket connection manager + DB poller
│       └── routers/               One router per resource
│           ├── portfolio.py
│           ├── orders.py
│           ├── signals.py
│           ├── cycles.py
│           ├── system.py
│           ├── agents.py
│           ├── backtest.py
│           ├── settings.py        GET/PUT  /api/settings/
│           ├── controls.py        GET/PATCH /api/controls/
│           └── market.py          GET /api/market/symbols and /ohlcv
├── tests/
│   ├── unit/                  Fast, in-memory tests (no external deps)
│   ├── integration/           End-to-end tests (mocked exchange)
│   └── backtest/              Backtest regression tests
├── scripts/
│   ├── backtest_runner.py     CLI entry point for backtesting
│   ├── dashboard.py           Entry point for FastAPI server
│   ├── stop_all.py            Kill lingering dev processes (ports 8000/3000) + remove lock files
│   └── capture_demo/          Playwright GIF capture (capture.py + README.md)
├── dashboard/                 Next.js frontend
│   └── src/
│       ├── app/               Page routes (Next.js App Router)
│       │   ├── page.tsx           Overview
│       │   ├── markets/page.tsx   Candlestick chart + ticker + symbol P&L bar
│       │   ├── pnl/page.tsx       Dedicated P&L page
│       │   ├── orders/page.tsx
│       │   ├── signals/page.tsx
│       │   ├── history/page.tsx
│       │   ├── agents/page.tsx
│       │   ├── controls/page.tsx  Execution / advisory toggles
│       │   ├── settings/page.tsx  Non-secret settings form
│       │   └── backtest/page.tsx
│       ├── components/
│       │   ├── CandlestickChart.tsx  lightweight-charts v5 wrapper
│       │   ├── PnLSummaryCards.tsx   5-metric summary cards (balance, unrealized, realized, fees, drawdown)
│       │   ├── RichEquityCurve.tsx   Tabbed equity curve (Balance / P&L Breakdown / Drawdown)
│       │   ├── ClosedTradesTable.tsx Sortable closed-trades journal
│       │   ├── TradeStatsBar.tsx     Aggregate trade statistics bar
│       │   ├── ThemeToggle.tsx       Light/Dark/System theme toggle
│       │   └── Providers.tsx         React Query + next-themes providers
│       ├── hooks/             React Query hooks + useWebSocket
│       ├── lib/api.ts         Typed API client
│       └── types/index.ts     TypeScript interfaces
├── examples/                  Annotated .env files for common setups
├── docs/                      MkDocs documentation site
├── Dockerfile                 Multi-stage backend image
├── dashboard/Dockerfile       Multi-stage frontend image
├── docker-compose.yml
├── pyproject.toml
└── Makefile
```

---

## 3. Development Setup

```bash
git clone https://github.com/cassiocouto/trading_crew.git
cd trading_crew

# Install all dependencies including dev tools
make dev

# Copy and configure secrets
cp .env.example .env
# Edit .env — at minimum set OPENAI_API_KEY

# Copy and configure non-secret settings (optional — defaults work for paper trading)
cp src/trading_crew/config/settings.yaml.example src/trading_crew/config/settings.yaml

# Verify the setup
make test
make lint
make type-check
```

`make dev` installs production + development + documentation + notification extras, and also installs the pre-commit hooks.

### Running the quality suite before committing

The CI pipeline runs four checks. Run them locally before pushing to avoid surprises:

```bash
make format        # Auto-format with ruff
make lint          # ruff check — must produce zero errors
make type-check    # mypy strict — must produce zero errors
make test          # All unit tests
```

Or run all at once:

```bash
make format; make lint; make type-check; make test
```

### Stopping lingering dev processes

When switching between dashboard sessions or if `make start` fails with "address already in use" or a Next.js lock-file error, run:

```bash
make stop
```

This executes `scripts/stop_all.py`, which kills any process listening on ports 8000 (API) or 3000 (UI) and removes `dashboard/.next/dev/lock`. Works on both Windows and Unix.

---

## 4. How a Trading Cycle Works

Understanding the cycle is the key to understanding the whole codebase.

### The entry point: `main.py`

`main.py` builds all services and crews once (at startup), then enters an `asyncio` event loop. Each iteration of the loop:

1. (Live mode only) Calls `_sync_balance_if_due()` — re-syncs `portfolio.balance_quote` from the exchange if `BALANCE_SYNC_INTERVAL_SECONDS` has elapsed since the last sync
2. Computes a `RunPlan` — which phases are due this cycle based on their independent schedules and the budget degrade state
3. Instantiates a fresh `TradingFlow` with the current state
4. Calls `await flow.akickoff()` — runs the entire cycle
5. Accumulates token usage and updates the budget counter
6. Sleeps for `LOOP_INTERVAL_SECONDS`

#### Portfolio balance seeding

At startup, the source of truth for `portfolio.balance_quote` depends on the trading mode:

- **Paper mode:** `balance_quote` is set to `INITIAL_BALANCE_QUOTE` from settings. This is the only mode where that setting has any effect.
- **Live mode:** `balance_quote` is seeded from `exchange_service.fetch_balance()` using the quote currency inferred from the first configured symbol (e.g. `BTC/USDT` → `USDT`). If the circuit breaker is open or the returned balance is zero, startup raises a `RuntimeError` with a clear diagnostic message.

#### Live wallet sync (`_sync_balance_if_due`)

`_sync_balance_if_due(exchange, portfolio, quote_currency, interval_seconds, drift_alert_threshold_pct, notifier, last_sync)` runs as a **pre-cycle step** — before any signal evaluation or order placement. This timing is deliberate: the trading loop is single-threaded `asyncio`, so updating `portfolio.balance_quote` before the cycle begins means no fill reconciliation is in progress, eliminating any staleness race.

The helper:
1. Returns immediately if the interval has not elapsed since `last_sync`
2. Calls `fetch_balance()` (no-op dict in paper mode, so the guard above is a safety net)
3. If the new balance differs from the in-memory value by more than `0.01`, updates `portfolio.balance_quote`, logs the drift, and optionally fires a `NotificationService.notify()` call when drift exceeds `BALANCE_DRIFT_ALERT_THRESHOLD_PCT`
4. Returns the updated `last_sync` timestamp

The `TradingFlow` is not reused across cycles. Each cycle gets a fresh instance with a fresh `CycleState`. The shared mutable state (portfolio, circuit breaker) is passed by reference.

### Inside `TradingFlow`

`TradingFlow` is a `crewai.flow.Flow[CycleState]` subclass. It defines four phases connected by routing methods:

```
market_phase()
    └─► route_after_market()
           ├── "halt"          → circuit_breaker_halt()
           ├── "skip_strategy" → post_cycle_hooks()
           └── "strategy"      → strategy_phase()
                                    └─► route_after_strategy()
                                           ├── "skip_execution" → post_cycle_hooks()
                                           └── "execution"      → execution_phase()
                                                                    └─► route_after_execution()
                                                                           └── post_cycle_hooks()
```

All phase methods are `async def`. Routing methods return plain strings that CrewAI Flow uses to decide which phase to call next.

### The `CycleState`

`CycleState` is the data contract between phases. It is a Pydantic `BaseModel` that lives in `models/cycle.py`. Each phase reads from and writes to it:

```python
class CycleState(BaseModel):
    cycle_number: int
    symbols: list[str]
    market_analyses: dict[str, MarketAnalysis]   # set by market_phase
    signals: list[TradeSignal]                    # set by strategy_phase
    risk_results: list[RiskCheckResult]           # set by strategy_phase
    order_requests: list[OrderRequest]            # set by strategy_phase
    orders: list[Order]                           # set by execution_phase
    filled_orders: list[Order]                    # set by execution_phase
    errors: list[str]
    circuit_breaker_tripped: bool
```

### Deterministic vs CrewAI pipelines

In `deterministic` mode, each phase calls a service directly (e.g. `self._market_svc.run_cycle()`). In `crewai` mode, it calls `crew.kickoff()` instead. In `hybrid` mode, it does both. The phase method itself does not care which path produced the data — it just reads from `self.state`.

---

## 5. Adding a Trading Strategy

This is the most common extension point. A strategy is a single class that receives pre-computed market analysis and returns a trade signal or `None`.

### Step 1: Create the strategy file

```python
# src/trading_crew/strategies/my_strategy.py
from __future__ import annotations

from typing import TYPE_CHECKING

from trading_crew.models.signal import SignalStrength, SignalType, TradeSignal
from trading_crew.strategies.base import BaseStrategy

if TYPE_CHECKING:
    from trading_crew.models.market import MarketAnalysis


class MyStrategy(BaseStrategy):
    """One-line description of what this strategy does."""

    name = "my_strategy"   # must be unique across all strategies

    def generate_signal(self, analysis: MarketAnalysis) -> TradeSignal | None:
        rsi = analysis.get_indicator("rsi_14")

        if rsi is None:
            return None   # always guard against missing indicators

        if rsi < 30:
            return TradeSignal(
                symbol=analysis.symbol,
                exchange=analysis.exchange,
                signal_type=SignalType.BUY,
                strength=SignalStrength.MODERATE,
                confidence=0.65,
                strategy_name=self.name,
                entry_price=analysis.current_price,
                reason=f"RSI oversold at {rsi:.1f}",
            )

        return None
```

### Step 2: Register it in `StrategyRunner`

Open `src/trading_crew/services/strategy_runner.py` and add your strategy to the default registry:

```python
from trading_crew.strategies.my_strategy import MyStrategy

DEFAULT_STRATEGIES: list[BaseStrategy] = [
    EMACrossoverStrategy(),
    BollingerBandsStrategy(),
    RSIRangeStrategy(),
    MACDCrossoverStrategy(),
    MyStrategy(),          # add here
]
```

That's it. On the next cycle, your strategy will run alongside the others.

### Available indicators in `MarketAnalysis`

Access indicators with `analysis.get_indicator(key)`. All values are `float | None`.

| Key | Description | Used by |
|-----|-------------|---------|
| `ema_fast` | 12-period EMA | `ema_crossover` |
| `ema_slow` | 50-period EMA | `ema_crossover` |
| `rsi_14` | 14-period RSI | `rsi_range` |
| `bb_upper` | Upper Bollinger Band (2σ, 20-period SMA) | `bollinger_bands` |
| `bb_middle` | Middle Bollinger Band (SMA 20) | `bollinger_bands` |
| `bb_lower` | Lower Bollinger Band | `bollinger_bands` |
| `macd_line` | MACD line (EMA12 − EMA26) | `macd_crossover` |
| `macd_signal` | 9-period EMA of MACD line | `macd_crossover` |
| `macd_histogram` | `macd_line − macd_signal` | `macd_crossover` |
| `atr_14` | 14-period ATR | stop-loss sizing |
| `range_high` | Highest high across all loaded candles | `rsi_range` |
| `range_low` | Lowest low across all loaded candles | `rsi_range` |

Other fields on `MarketAnalysis`:

```python
analysis.symbol          # e.g. "BTC/USDT"
analysis.exchange        # e.g. "binance"
analysis.current_price   # latest close price
analysis.regime          # "trending", "ranging", "volatile", "unknown"
analysis.metadata        # dict — includes sentiment data if enabled
```

### Step 3: Add unit tests

```python
# tests/unit/strategies/test_my_strategy.py
from datetime import UTC, datetime

import pytest

from trading_crew.models.market import MarketAnalysis
from trading_crew.models.signal import SignalType
from trading_crew.strategies.my_strategy import MyStrategy


def _make_analysis(rsi: float) -> MarketAnalysis:
    return MarketAnalysis(
        symbol="BTC/USDT",
        exchange="binance",
        timestamp=datetime.now(UTC),
        current_price=60000.0,
        indicators={"rsi_14": rsi},
    )


def test_buy_signal_on_oversold():
    signal = MyStrategy().generate_signal(_make_analysis(rsi=25.0))
    assert signal is not None
    assert signal.signal_type == SignalType.BUY


def test_no_signal_on_neutral():
    signal = MyStrategy().generate_signal(_make_analysis(rsi=50.0))
    assert signal is None
```

Run: `make test-unit`

### Confidence scoring guidelines

Confidence is a float in `[0.0, 1.0]`. The risk pipeline will reject signals below `min_confidence` (default 0.5). As a convention:

- `0.5–0.65` — marginal signal; conditions are present but weak
- `0.65–0.80` — moderate conviction
- `0.80–0.95` — strong conviction
- Avoid `1.0` — nothing is ever 100% certain

### Step 4: Add a dashboard overlay (optional)

The Markets page in the dashboard can display your strategy's indicator lines
directly on the candlestick chart.  This step is purely cosmetic — the bot
runs fine without it — but it is strongly recommended for any strategy that is
maintained long-term.

**Where the config lives:** `dashboard/src/app/markets/page.tsx`, in the
`STRATEGY_DEFS` constant near the top of the file.  Each entry implements the
`StrategyDef` interface:

```ts
interface StrategyDef {
  id: string;               // must match the strategy's `name` attribute
  label: string;            // display name for the toggle pill
  color: string;            // primary colour (used for the pill border)
  description: string;      // shown in the ? help tooltip
  indicatorLabels: string[]; // shown on the native tooltip on hover
  buildOverlays: (bars: OHLCVBar[]) => OverlayLine[];
}
```

**`OverlayLine` fields:**

| Field | Type | Description |
|---|---|---|
| `id` | `string` | Stable key (used for imperative series tracking — must be unique) |
| `label` | `string` | Shown in the chart crosshair legend |
| `color` | `string` | Line colour (hex) |
| `lineStyle` | `"solid" \| "dashed" \| "dotted"` | Optional; defaults to solid |
| `type` | `"line" \| "histogram"` | Optional; defaults to `"line"` |
| `data` | `{ time: number; value: number; color?: string }[]` | Time-aligned values |
| `pane` | `number` | 0 = main price pane (default), 1 = first sub-pane, 2 = second |
| `priceScaleId` | `string` | Price scale identifier; use a unique id for oscillators |

**Pane conventions:**
- `pane: 0` — overlays on the main candlestick chart (EMA, Bollinger, price levels)
- `pane: 1` — first sub-pane, for 0–100 oscillators such as RSI
- `pane: 2` — second sub-pane, for zero-centred oscillators such as MACD

**Example — adding `my_strategy` with an RSI overlay:**

```ts
// In STRATEGY_DEFS inside dashboard/src/app/markets/page.tsx:
{
  id: "my_strategy",        // matches MyStrategy.name
  label: "My Strategy",
  color: "#6366f1",
  description: "Buys when RSI dips below 30 and …",
  indicatorLabels: ["RSI 14"],
  buildOverlays: (bars) => {
    const rsiData = rsiAligned(bars, 14);          // from @/lib/indicators
    const obLine = rsiData.map((d) => ({ ...d, value: 30 }));
    return [
      {
        id: "my-rsi",
        label: "RSI 14",
        color: "#6366f1",
        data: rsiData,
        pane: 1,
        priceScaleId: "my-rsi",
      },
      {
        id: "my-rsi-os",
        label: "Oversold (30)",
        color: "#ef4444",
        lineStyle: "dashed",
        data: obLine,
        pane: 1,
        priceScaleId: "my-rsi",
      },
    ];
  },
},
```

**Adding a new indicator computation:**

If your strategy uses an indicator not already in `dashboard/src/lib/indicators.ts`,
add it there using the same rolling-window approach as the existing helpers.
Mirror the exact formula from `TechnicalAnalyzer` in Python so the chart
overlay matches the backend's decision values.

---

## 6. Adding a New Indicator

Indicators are computed by `TechnicalAnalyzer` in `services/technical_analysis.py`. The analyser uses `pandas-ta` and stores results in `MarketAnalysis.indicators`.

To add a new indicator:

1. Open `src/trading_crew/services/technical_analysis.py`
2. In the `analyze()` method, compute your indicator using `pandas-ta` on the `df` DataFrame
3. Add it to the `indicators` dict with a meaningful key
4. Document the key in the strategy-writing guide

Example — adding VWAP:

```python
# In TechnicalAnalyzer.analyze():
vwap = df.ta.vwap()
if vwap is not None and not vwap.empty:
    indicators["vwap"] = float(vwap.iloc[-1])
```

Your strategies can then access it with `analysis.get_indicator("vwap")`.

---

## 7. The Agent and Tool System

CrewAI agents are defined in two places:

- **`config/agents.yaml`** — role, goal, and backstory (plain text, no code)
- **`agents/<name>.py`** — Python factory function that creates the `crewai.Agent` with the right tools

Tools are thin wrappers in `tools/` that expose service methods to agents via `crewai.tools.BaseTool`. Each tool validates its inputs with Pydantic and delegates to a service.

### How agents receive services

Services are passed to agent factory functions at startup. The factory attaches tools that close over those service instances:

```python
# agents/executor.py
def create_executor_agent(
    exchange_service: ExchangeService,
    db_service: DatabaseService,
    notification_service: NotificationService,
    agent_config: dict[str, str],
) -> Agent:
    tools = [
        CreateOrderTool(exchange_service=exchange_service, db_service=db_service),
        ...
    ]
    return Agent(role=..., tools=tools, ...)
```

This means agents are created once at startup and reused across cycles. Tools hold references to the shared service instances.

---

## 8. Adding a CrewAI Tool

A tool lets an agent call a service method. Tools are in `src/trading_crew/tools/`.

### Structure

```python
# src/trading_crew/tools/my_tool.py
from __future__ import annotations

from pydantic import BaseModel, Field
from crewai.tools import BaseTool

from trading_crew.services.my_service import MyService


class MyToolInput(BaseModel):
    symbol: str = Field(..., description="The trading pair, e.g. BTC/USDT")


class MyTool(BaseTool):
    name: str = "my_tool"
    description: str = "One sentence explaining what this tool does and when to use it."
    args_schema: type[BaseModel] = MyToolInput

    my_service: MyService

    def _run(self, symbol: str) -> str:
        result = self.my_service.do_something(symbol)
        return str(result)
```

### Guidelines

- **Keep tool descriptions clear and actionable.** Agents use the description to decide when to call a tool.
- **Return strings.** CrewAI agents receive tool output as text. Format it clearly (short summaries, not raw JSON dumps).
- **Never raise exceptions from `_run`.** Catch exceptions and return a descriptive error string so the agent can handle it gracefully.
- **Input schemas must be Pydantic models.** Every field needs a `description` so the LLM knows what to pass.

---

## 9. The Database Layer

The database is accessed through two layers:

- **`db/models.py`** — SQLAlchemy ORM models (the table definitions)
- **`services/database_service.py`** — high-level operations (the public API used by the rest of the code)

The `DatabaseService` manages its own sessions. Callers never touch sessions directly — they call methods like `save_ticker()`, `get_recent_orders()`, `save_cycle_summary()`.

### ORM models

| Model | Table | Purpose |
|-------|-------|---------|
| `TickerRecord` | `tickers` | Spot price snapshots |
| `OHLCVRecord` | `ohlcv` | Candlestick data |
| `TradeSignalRecord` | `trade_signals` | Generated signals |
| `OrderRecord` | `orders` | Order lifecycle |
| `FailedOrderRecord` | `failed_orders` | Dead-letter rejected orders |
| `PortfolioRecord` | `portfolio_snapshots` | Portfolio state per cycle |
| `PnLSnapshotRecord` | `pnl_snapshots` | P&L curve points |
| `CycleRecord` | `cycle_history` | Per-cycle summary |

### Session management

```python
from trading_crew.db.session import get_session

with get_session(engine) as session:
    session.add(record)
    # auto-commits on exit, rolls back on exception
```

`get_session` is a context manager that commits on clean exit and rolls back on any exception. Never call `session.commit()` manually inside — it is called for you.

---

## 10. Adding a Database Migration

When you add or change an ORM model, you need a migration:

```bash
# Generate the migration automatically from model changes
make db-migrate msg="add my_new_column to orders"

# Review the generated file in src/trading_crew/db/migrations/versions/
# Then apply it:
make db-upgrade
```

Alembic compares the current database schema against the ORM models and generates the diff as a migration script. Always review the auto-generated file before applying — auto-generate can miss some edge cases (e.g. column renames, complex constraints).

To roll back the last migration:

```bash
make db-downgrade
```

---

## 11. The API and Dashboard Backend

The FastAPI app is in `src/trading_crew/api/`. It runs as a separate process from the trading bot and reads from the same database (read-only for most endpoints).

### Adding a new endpoint

1. Create or extend a router in `api/routers/`
2. Register it in `api/app.py` with `app.include_router(..., prefix="/api/your-resource")`
3. Add a Pydantic response schema in `api/schemas.py`

Example:

```python
# api/routers/my_resource.py
from fastapi import APIRouter, Depends
from trading_crew.api.deps import get_db
from trading_crew.api.schemas import MyResponse

router = APIRouter(tags=["my_resource"])

@router.get("/", response_model=list[MyResponse])
def get_my_resource(db: DatabaseService = Depends(get_db)) -> list[MyResponse]:
    ...
```

### WebSocket events

The WebSocket poller in `api/websocket.py` emits events by comparing the current max DB row IDs against per-connection watermarks. To add a new event type:

1. Add the event type string to `WsEvent` in `api/schemas.py`
2. Add a query block in `_collect_events()` that detects the new condition
3. Update the frontend's event handler in `dashboard/src/`

### Symbol filtering on read endpoints

Five endpoints accept an optional `?symbol=` query parameter to scope results to a single trading pair:

| Endpoint | Symbol param | Notes |
|----------|-------------|-------|
| `GET /api/orders/` | `?symbol=BTC%2FUSDT` | Combined with optional `?status=` filter |
| `GET /api/orders/failed` | `?symbol=BTC%2FUSDT` | Combined with `?unresolved_only=` flag |
| `GET /api/signals/` | `?symbol=BTC%2FUSDT` | Combined with optional `?strategy=` filter |
| `GET /api/portfolio/trades` | `?symbol=BTC%2FUSDT` | Closed trades via FIFO lot-matching; also accepts `?limit=` |
| `GET /api/portfolio/trade-stats` | `?symbol=BTC%2FUSDT` | Aggregate metrics from closed trades |

All five are backward-compatible — omitting `symbol` returns data across all symbols. The Markets page sidebar and P&L bar use the symbol filter; the dedicated P&L page fetches without a symbol to get the full picture.

### P&L and trade-matching endpoints

The portfolio router (`api/routers/portfolio.py`) provides three P&L-related endpoints:

| Endpoint | Response schema | Description |
|----------|----------------|-------------|
| `GET /api/portfolio/` | `PortfolioResponse` | Enriched with `total_balance_quote` (cash + market value) and `unrealized_pnl` |
| `GET /api/portfolio/trades` | `list[ClosedTradeResponse]` | Closed trades via FIFO lot-matching of filled `OrderRecord`s |
| `GET /api/portfolio/trade-stats` | `TradeStatsResponse` | Aggregate stats: total trades, win rate, profit factor, avg hold |

#### FIFO lot-matching algorithm

Closed trades are not stored in a separate table — they are computed on-the-fly from filled orders by `_build_closed_trades()` in `api/routers/portfolio.py`. The algorithm:

1. Queries all filled `OrderRecord`s ordered by `created_at`, optionally filtered by symbol
2. Extracts each row into a lightweight `_OrderTuple` dataclass **within** the SQLAlchemy session (avoids `DetachedInstanceError`)
3. Skips orders with zero `filled_amount` or zero `average_fill_price`
4. BUY orders are pushed onto a per-symbol FIFO queue as `_BuyLot` instances
5. SELL orders consume lots from the front of the queue:
   - Each SELL may match against one or more buy lots (partial fills supported)
   - Fee allocation is proportional: `lot.fee × (matched / lot.amount)` for the entry side
   - A `ClosedTradeResponse` is emitted for each matched portion
6. Results are sorted by `closed_at` descending and truncated to the requested `limit`

This is the same core algorithm used by `SimulationRunner._build_trades()` in backtesting, adapted for the API context.

#### Frontend data flow

```
usePortfolio()        → GET /api/portfolio/         → PnLSummaryCards (balance, unrealized)
usePnlHistory(200)    → GET /api/portfolio/history   → RichEquityCurve (equity, P&L breakdown, drawdown)
useClosedTrades(200)  → GET /api/portfolio/trades    → ClosedTradesTable
useTradeStats()       → GET /api/portfolio/trade-stats → TradeStatsBar
```

The Markets page uses `usePortfolio()` and `useClosedTrades(1000, selectedSymbol)` to populate the symbol-scoped P&L bar.

### Routers that write outside the database

Two routers write to files rather than the database:

- **`routers/settings.py`** (`PUT /api/settings/`) — writes to `config/settings.yaml` atomically using a temp file + `os.replace()`, then calls `clear_settings_cache()` to bust the `lru_cache` on `get_settings()`.
- **`routers/controls.py`** (`PATCH /api/controls/`) — writes to `config/runtime.yaml` via `runtime_flags.write()` (threading lock + `os.replace()`), then broadcasts a `controls_updated` WebSocket event.

Both routers use the same atomic write pattern to prevent partial writes if the process is killed mid-write.

### Dashboard theming (dark mode)

The dashboard uses `next-themes` for theme management and Tailwind v4's class-based `dark:` variant (configured via `@custom-variant dark` in `globals.css`). The `<html>` element receives a `dark` class when the dark theme is active, which activates all `dark:*` Tailwind utilities.

When adding or editing dashboard components, always include `dark:` counterparts for hardcoded light colors. The standard mappings are:

- `bg-white` → `dark:bg-gray-900`, `bg-gray-50` → `dark:bg-gray-950`
- `border-gray-200` → `dark:border-gray-700`, `border-gray-100` → `dark:border-gray-800`
- `text-gray-900` → `dark:text-gray-100`, `text-gray-700` → `dark:text-gray-300`
- Status badges use opacity-based backgrounds: `dark:bg-{color}-500/15 dark:text-{color}-400`
- Form inputs: `dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100`

For chart libraries that use imperative JavaScript APIs (e.g. `lightweight-charts`), import `useTheme()` from `next-themes` and pass `resolvedTheme`-dependent color constants to chart options. See `CandlestickChart.tsx` and `EquityCurve.tsx` for examples.

### Accessing `db._engine` from routers

All routers receive a `DatabaseService` instance via `Depends(get_db)` and access the underlying engine with `db._engine` to run raw SQLAlchemy queries. This is intentional — it keeps the database connection lifecycle managed by the service, while still allowing the API layer to use the full SQLAlchemy query API.

---

## 12. Testing

### Test structure

```
tests/
├── unit/          Fast, isolated tests (no I/O)
├── integration/   Full-flow tests with mocked async exchange
└── backtest/      Backtest regression tests (run against local DB)
```

### Running tests

```bash
make test              # All tests
make test-unit         # Unit tests only  (fast, ~5s)
make test-integration  # Integration tests (slower, ~30s)
make backtest          # Backtest regression tests
```

### Writing unit tests

Unit tests live in `tests/unit/`. They should be fast (no network, no file I/O, no sleep). Use `unittest.mock.MagicMock` and `AsyncMock` for dependencies.

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_something():
    mock_exchange = MagicMock()
    mock_exchange.fetch_ticker = AsyncMock(return_value=Ticker(...))
    ...
```

Mark unit tests with `@pytest.mark.unit` if you want to run them selectively with `make test-unit`.

### Writing integration tests

Integration tests live in `tests/integration/`. They run the full `TradingFlow` with a mocked CCXT exchange and a real in-memory SQLite database. See `tests/integration/test_full_cycle.py` as a reference.

Key patterns:

- Use `@pytest.mark.asyncio` for async tests
- Inject a real `Engine` object directly into `DatabaseService` to use an isolated test DB
- Mock `ccxt.async_support` at the module level so no real network calls happen
- Assert on `CycleState` fields after `flow.akickoff()` completes

### Async fixtures

```python
import pytest_asyncio

@pytest_asyncio.fixture
async def db_service():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    service = DatabaseService(engine)
    yield service
    engine.dispose()
```

---

## 13. Code Standards

### Type annotations

All public functions, methods, and class attributes must have type annotations. The codebase runs mypy in strict mode — every function must be fully typed.

```python
# good
def compute_size(price: float, budget: float) -> float:
    return budget / price

# bad — missing return type
def compute_size(price, budget):
    return budget / price
```

Use `from __future__ import annotations` at the top of every file. This defers annotation evaluation, allowing forward references and imports that live only in `TYPE_CHECKING` blocks.

### Import hygiene

- Imports used only for type annotations go inside `if TYPE_CHECKING:` blocks
- Third-party imports used only for typing go there too (this is enforced by ruff rule `TC002/TC003`)
- Import order: stdlib → third-party → local (enforced by ruff `I001`)

### Docstrings

Public modules, classes, and functions need docstrings. Use Google style:

```python
def my_function(x: int, y: float) -> str:
    """One-line summary.

    Longer description if needed.

    Args:
        x: Description of x.
        y: Description of y.

    Returns:
        Description of return value.

    Raises:
        ValueError: When x is negative.
    """
```

### Error handling

- Never catch bare `Exception` unless you re-raise it or log it explicitly
- Services log warnings/errors and return safe defaults where possible
- Tools catch service errors and return error strings to the agent

### Async conventions

All service methods that call external APIs are `async def`. Internal computation methods are synchronous. The general rule: if it involves I/O, it's async.

When offloading sync work from async context, use `asyncio.to_thread()`:

```python
result = await asyncio.to_thread(my_sync_function, arg1, arg2)
```

---

## 14. Configuration Internals

### Two-layer configuration model

Configuration is split into two layers:

| Layer | File | Contents | Version-controlled? |
|-------|------|----------|---------------------|
| **Secrets** | `.env` | API keys, tokens, `DATABASE_URL`, `DASHBOARD_API_KEY` | No (gitignored) |
| **Non-secret settings** | `settings.yaml` | All other configuration | No (gitignored) |

`settings.yaml.example` is the version-controlled template. Copy it to create `settings.yaml`:

```bash
cp src/trading_crew/config/settings.yaml.example src/trading_crew/config/settings.yaml
```

### Priority order (highest wins)

```
environment variables  >  .env file  >  settings.yaml  >  code defaults
```

This means any setting in `.env` or an environment variable overrides the `settings.yaml` value — useful for container deployments where you inject configuration via environment.

### Nested settings

Risk parameters use the double-underscore prefix when set via env vars:

```env
RISK__MAX_DRAWDOWN_PCT=10
RISK__DEFAULT_STOP_LOSS_PCT=2
```

The same values can be set in `settings.yaml` using nested YAML:

```yaml
risk:
  max_drawdown_pct: 10
  default_stop_loss_pct: 2
```

### Runtime control flags

Two special flags live in `config/runtime.yaml` (also gitignored):

| Flag | Effect |
|------|--------|
| `execution_paused: true` | Bot skips the execution phase each cycle — no orders placed |
| `advisory_paused: true` | Advisory crew is bypassed regardless of uncertainty score |

The bot re-reads `runtime.yaml` at the start of each cycle, so changes take effect within one cycle interval without a restart. The dashboard Controls page writes to this file via `PATCH /api/controls`.

`runtime.yaml` is created automatically with safe defaults if missing.

### Adding a new setting

1. Add a field to `Settings` (or `RiskParams`) in `config/settings.py`
2. Add a default value — never leave a required field without a sane default
3. Add the field to `settings.yaml.example` with a comment
4. If the field is non-secret and dashboard-editable, add it to `SettingsResponse` and `SettingsUpdate` in `api/schemas.py`
5. Update `docs/docs/configuration.md`

```python
# In settings.py
class Settings(BaseSettings):
    my_new_setting: int = Field(default=100, description="What this does")
```

Access it anywhere via `get_settings().my_new_setting`.

### Cache invalidation

`get_settings()` is cached with `@lru_cache`. The `PUT /api/settings` endpoint calls `clear_settings_cache()` after writing `settings.yaml` so the API process picks up the new values immediately. The trading bot process uses its startup-cached copy until it restarts.

### Advisory crew LLM key guard

`settings.advisory_llm_configured` returns `True` when `OPENAI_API_KEY` is set to a non-placeholder value. The advisory crew is disabled at startup and cannot be unpaused via the Controls page when this returns `False`.

### Uncertainty scorer internals

**File:** `src/trading_crew/services/uncertainty_scorer.py`

`UncertaintyScorer.score()` is called once per cycle from `TradingFlow` after the deterministic pipeline completes. It is **pure and synchronous** — no I/O, no LLM calls.

#### Formula

```
score = clamp(
    Σ (raw_i × weight_i)   for i in [volatile_regime, sentiment_extreme,
                                       low_sentiment_confidence, strategy_disagreement,
                                       drawdown_proximity, regime_change]
, 0.0, 1.0)
```

If `score >= activation_threshold` → `UncertaintyResult.recommend_advisory = True` → advisory crew runs.

#### Factor implementations

| Factor | Class method | Raw value computation |
|--------|-------------|----------------------|
| `volatile_regime` | `_volatile_regime` | `count(regime == "volatile") / total_symbols` — fraction of symbols in a volatile regime this cycle |
| `sentiment_extreme` | `_sentiment_extreme` | Binary: `1.0` if `abs(sentiment.score) >= 0.5`, else `0.0`. Skipped when sentiment is disabled or confidence is zero |
| `low_sentiment_confidence` | `_low_sentiment_confidence` | Binary: `1.0` if `(1 - sentiment.confidence) >= 0.5`, else `0.0`. Skipped when no sentiment snapshot |
| `strategy_disagreement` | `_strategy_disagreement` | Per symbol: `1 - (max_faction / n_votes)`, averaged across all symbols. Zero when all strategies agree |
| `drawdown_proximity` | `_drawdown_proximity` | `min(1.0, portfolio.drawdown_pct / risk_params.max_drawdown_pct)`. Zero when at peak; 1.0 at the circuit-breaker limit |
| `regime_change` | `_regime_change` | `changed_symbols / compared_symbols` since previous cycle regimes. Zero on first cycle (no previous state) |

#### Default weights and saturation

```python
# UncertaintyWeights defaults
volatile_regime           = 0.3
sentiment_extreme         = 0.2
low_sentiment_confidence  = 0.2
strategy_disagreement     = 0.3
drawdown_proximity        = 0.2
regime_change             = 0.3
# Sum = 1.5  (intentionally > 1.0)
```

Weights intentionally sum to **1.5** so that multiple simultaneously firing factors push the score toward 1.0 more aggressively than any single factor could (max single-factor contribution is 0.3, below the default threshold of 0.6). A single factor cannot trigger the advisory crew alone at default settings.

#### Data flow

```
TradingFlow.strategy_phase()
  └─ analyses, votes, portfolio, risk_params, sentiment, previous_regimes
       │
       ▼
UncertaintyScorer.score()          ← no I/O, pure computation
       │
       ├─ UncertaintyResult.score            stored on CycleRecord
       ├─ UncertaintyResult.factors          logged for debugging
       └─ UncertaintyResult.recommend_advisory
              │
              ├─ False → skip advisory crew entirely
              └─ True  → TradingFlow.advisory_phase() → CrewAI crew
```

#### Advisory crew lifecycle

The advisory crew is **stateless and short-lived**. There is no background process, no "active mode", and no explicit transition back to idle. The lifecycle per cycle is:

```
main.py while-loop (one iteration = one cycle)
  │
  ├─ rt_flags = runtime_flags.read()           # check dashboard pauses
  │
  ├─ _effective_advisory_crew = None           # if advisory_paused=true, crew is None
  │    else advisory_crew                      # (or None if advisory_enabled=false / no API key)
  │
  └─ TradingFlow.akickoff()
        ├─ market_phase → strategy_phase → compute_uncertainty
        │
        ├─ route_after_uncertainty:
        │     score < threshold  →  "skip_advisory"  (crew never called this cycle)
        │     score ≥ threshold AND crew is not None AND budget not exhausted
        │                         →  "advisory"
        │
        ├─ advisory_phase (only if routed to "advisory"):
        │     crew.run(context)  ←  one blocking async call to the LLM
        │     apply directives   ←  adjusts signals in-place
        │     (done — crew object is reused next cycle from the outer loop)
        │
        └─ reserve_phase → execution_phase → post_cycle_hooks
```

The `AdvisoryCrew` instance is created **once** at startup in `main()` and reused across all cycles. Between cycles it is entirely idle. Calling `crew.run()` is what constitutes "active" — it begins and ends within a single cycle.

**Returning to idle is automatic.** No reset, no state to clear. The next cycle simply re-evaluates the uncertainty score from scratch. If conditions have normalised, `recommend_advisory` will be `False` and `advisory_phase` will not be reached.

**Budget accounting** (`_accumulate_estimated_tokens`) runs after each cycle. If `daily_token_budget_enabled` is true and `estimated_tokens_used_today >= daily_token_budget_tokens`:
- `budget_stop` mode: `budget_state.degrade_level` is set to `BudgetDegradeLevel.BUDGET_STOP`. The `route_after_uncertainty` router checks this and routes to `"skip_advisory"` for the rest of the UTC day.
- `normal` mode: advisory continues; a warning notification is sent once.
- At UTC midnight, `_refresh_budget_day` resets `estimated_tokens_used_today = 0` and `degrade_level = NORMAL`.

#### Modifying or extending factors

1. Add a new `_my_factor()` method on `UncertaintyScorer` returning `UncertaintyFactor`.
2. Add the corresponding weight field to `UncertaintyWeights` with a sane default.
3. Add the weight field to `Settings` (prefix `uncertainty_weight_`) and `settings.yaml.example`.
4. Wire the new field into the `UncertaintyWeights` construction in `TradingFlow`.
5. Call `factors.append(self._my_factor(...))` inside `score()`.
6. Add the new weight field to `SettingsResponse` / `SettingsUpdate` in `api/schemas.py` so it is dashboard-editable.

---

## 15. Docker and Deployment

### Building images

```bash
make docker-build
```

This builds both the Python backend image and the Next.js frontend image using multi-stage Dockerfiles.

### Running with Docker Compose

```bash
# Start all services
make docker-up

# View logs
docker compose logs -f trading-bot
docker compose logs -f api
docker compose logs -f dashboard

# Stop
make docker-down
```

The `docker-compose.yml` defines three services:

| Service | Image | Default port |
|---------|-------|-------------|
| `trading-bot` | `trading-crew:latest` | — |
| `api` | `trading-crew:latest` | 8000 |
| `dashboard` | `trading-crew-dashboard:latest` | 3000 |

All three share a `./data` volume for the SQLite database. For production, replace SQLite with PostgreSQL — see the commented-out section in `docker-compose.yml`.

### Dev container

A `.devcontainer/devcontainer.json` is included for VS Code and GitHub Codespaces. It configures Python 3.12, Node 20, `uv`, and all recommended extensions automatically on container start.

### Production checklist

- [ ] Set `trading_mode: "paper"` in `settings.yaml` first; validate for multiple days before switching to `live`
- [ ] Use PostgreSQL (`DATABASE_URL=postgresql+psycopg2://...` in `.env`) instead of SQLite
- [ ] Run `make db-upgrade` before starting the app against a new database
- [ ] Set `DASHBOARD_API_KEY` in `.env` to protect the REST API
- [ ] Mount the data directory as a persistent volume
- [ ] Configure Telegram notifications for error alerts (`TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` in `.env`)
- [ ] Set `log_level: "WARNING"` in `settings.yaml` to reduce log volume in production
- [ ] Create an exchange API key with trade permissions only — never withdrawal permissions
- [ ] Monitor the equity curve via the dashboard or `pnl_snapshots` table

---

## 16. CI/CD Pipeline

The CI pipeline (`.github/workflows/ci.yml`) runs on every push to `main` and on all pull requests. It has four jobs that run in parallel:

| Job | What it runs |
|-----|-------------|
| **Lint & Format** | `ruff check src/ tests/` and `ruff format --check src/ tests/` |
| **Type Check** | `mypy src/` (strict mode) |
| **Unit Tests** | `pytest -m "not integration and not backtest"` |
| **Integration Tests** | `pytest -m integration` (runs after Unit Tests) |

All four must pass before a PR can be merged.

### Release automation

`.github/workflows/release.yml` triggers on version tags (`v*.*.*`):

1. Runs the full test suite
2. Publishes the Python package to PyPI (OIDC keyless auth)
3. Builds and pushes Docker images to GitHub Container Registry
4. Creates a GitHub Release with auto-generated notes

To create a release:

```bash
git tag v0.9.0
git push origin v0.9.0
```

---

## 17. Key Extension Points Summary

| What you want to do | Where to look |
|--------------------|--------------|
| Add a trading strategy | `strategies/` → inherit `BaseStrategy`, register in `strategy_runner.py` |
| Add a technical indicator | `services/technical_analysis.py` → compute in `analyze()`, add to `indicators` dict |
| Add a new CrewAI tool | `tools/` → inherit `BaseTool`, add to the relevant agent factory in `agents/` |
| Add a new CrewAI agent | `agents/` → create factory, add agent to the relevant crew in `crews/` |
| Add a risk check | `risk/` → implement check, wire it into `services/risk_pipeline.py` |
| Add a custom sell guard | `risk/sell_guard.py` → subclass `SellGuard`, implement `evaluate()`, pass to `RiskPipeline(sell_guard=...)` in `main.py` |
| Add a new API endpoint | `api/routers/` → add router, register in `api/app.py` |
| Add a P&L metric card | `PnLSummaryCards.tsx` → add a `<Card>` entry; data comes from `PortfolioResponse` or `PnLPointResponse` |
| Add a closed-trade column | `ClosedTradesTable.tsx` → add column to header + body rows; extend `ClosedTradeResponse` schema if needed |
| Add a WebSocket event | `api/websocket.py` + `api/schemas.py` + `useWebSocket.ts` frontend handler |
| Add a new database table | `db/models.py` → define ORM model, `make db-migrate msg="..."` |
| Add a new notification channel | `services/notification_service.py` → add backend, call in relevant hooks |
| Add a configuration option | `config/settings.py` + `settings.yaml.example` + `api/schemas.py` (SettingsResponse/Update) |

### Adding a custom sell guard

`SellGuard` in `risk/sell_guard.py` is a first-class extension point:

```python
from trading_crew.risk.sell_guard import SellGuard
from trading_crew.models.risk import RiskParams

class MinProfitSellGuard(SellGuard):
    def evaluate(self, symbol, proposed_price, break_even_price, risk_params):
        if break_even_price is None:
            return True, "no break-even on record"
        min_sell = break_even_price * (1 + risk_params.min_profit_margin_pct / 100)
        if proposed_price < min_sell:
            return False, f"need {min_sell:.4f}, proposed {proposed_price:.4f}"
        return True, "ok"
```

Then in `main.py`, replace the `sell_guard` instantiation and pass your guard to `RiskPipeline`.

**How break-even prices reach the guard:** `TradingFlow.strategy_phase()` calls `db.get_break_even_prices(held_symbols)` once per cycle (single batched DB query) and passes the result as `break_even_prices` to `risk_pipeline.evaluate()`. The pipeline forwards the per-symbol value to the guard — no further DB access inside the pipeline.

**How break-even is computed:** `ExecutionService._compute_break_even(order)` runs when a BUY order reaches `FILLED` status in `_reconcile_fill()`:
```
break_even_price = average_fill_price + (total_fee / filled_amount)
```
The value is stored in `orders.break_even_price` (nullable Float column) via `save_order()`. Old rows without the column remain `NULL` and the guard falls through gracefully.

---

*For end-user documentation, see [USER_MANUAL.md](USER_MANUAL.md).*
*For the architecture overview, see [ARCHITECTURE.md](ARCHITECTURE.md).*
*For contributing guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).*
