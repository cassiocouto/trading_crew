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
│   │   ├── settings.py        Pydantic Settings (all env vars)
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
│   │   ├── bollinger.py
│   │   ├── rsi_range.py
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
│   │   └── portfolio_limits.py    Exposure and concentration checks
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
│           └── agents.py
├── tests/
│   ├── unit/                  Fast, in-memory tests (no external deps)
│   ├── integration/           End-to-end tests (mocked exchange)
│   └── backtest/              Backtest regression tests
├── scripts/
│   ├── backtest_runner.py     CLI entry point for backtesting
│   └── dashboard.py           Entry point for FastAPI server
├── dashboard/                 Next.js frontend
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

# Copy and configure environment
cp .env.example .env
# Edit .env — at minimum set OPENAI_API_KEY

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
    MyStrategy(),          # add here
]
```

That's it. On the next cycle, your strategy will run alongside the others.

### Available indicators in `MarketAnalysis`

Access indicators with `analysis.get_indicator(key)`. All values are `float | None`.

| Key | Description |
|-----|-------------|
| `ema_fast` | 12-period EMA |
| `ema_slow` | 50-period EMA |
| `rsi_14` | 14-period RSI |
| `bb_upper` | Upper Bollinger Band (2σ, 20-period) |
| `bb_middle` | Middle Bollinger Band (SMA 20) |
| `bb_lower` | Lower Bollinger Band |
| `macd` | MACD line |
| `macd_signal` | MACD signal line |
| `macd_hist` | MACD histogram |
| `atr_14` | 14-period ATR |
| `range_high` | Recent candle high |
| `range_low` | Recent candle low |

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

Configuration is managed by `config/settings.py` using `pydantic-settings`. All settings are read from environment variables at startup. Nested settings (like risk parameters) use a double-underscore prefix:

```env
RISK__MAX_DRAWDOWN_PCT=10
RISK__DEFAULT_STOP_LOSS_PCT=2
```

To add a new setting:

1. Add a field to the relevant `Settings` class or nested model in `config/settings.py`
2. Add a default value (never leave a required field without a sane default)
3. Document it in `.env.example` with a comment
4. Update `docs/docs/configuration.md`

```python
# In settings.py
class Settings(BaseSettings):
    my_new_setting: int = Field(default=100, description="What this does")
```

Access it anywhere via `get_settings().my_new_setting`.

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

- [ ] Set `TRADING_MODE=paper` first; validate for multiple days before switching to `live`
- [ ] Use PostgreSQL (`DATABASE_URL=postgresql+psycopg2://...`) instead of SQLite
- [ ] Run `make db-upgrade` before starting the app against a new database
- [ ] Set `DASHBOARD_API_KEY` to protect the REST API
- [ ] Mount the data directory as a persistent volume
- [ ] Configure Telegram notifications for error alerts
- [ ] Set `LOG_LEVEL=WARNING` in production to reduce log volume
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
| Add a new API endpoint | `api/routers/` → add router, register in `api/app.py` |
| Add a WebSocket event | `api/websocket.py` + `api/schemas.py` + frontend handler |
| Add a new database table | `db/models.py` → define ORM model, `make db-migrate msg="..."` |
| Add a new notification channel | `services/notification_service.py` → add backend, call in relevant hooks |
| Add a configuration option | `config/settings.py` + `.env.example` + `docs/docs/configuration.md` |

---

*For end-user documentation, see [USER_MANUAL.md](USER_MANUAL.md).*
*For the architecture overview, see [ARCHITECTURE.md](ARCHITECTURE.md).*
*For contributing guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).*
