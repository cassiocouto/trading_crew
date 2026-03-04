# Architecture

This document explains the high-level design of Trading Crew to help new
contributors navigate the codebase.

## Design Philosophy

Trading Crew follows three core principles:

1. **Safety first** — paper trading by default, risk checks on every signal
2. **Separation of concerns** — each agent has one job, crews coordinate agents
3. **Pluggability** — strategies, exchanges, and notifications are swappable

## System Overview

```
┌─────────────────────────────────────────────────────┐
│                  CrewAI Flow Engine                  │
│            (Orchestration + State Machine)           │
├──────────┬──────────────────┬───────────────────────┤
│          │                  │                       │
│  Market Intelligence   Strategy Crew    Execution Crew
│       Crew                                         │
│  ┌────────────┐   ┌──────────────┐   ┌───────────┐│
│  │  Sentinel   │   │  Strategist  │   │  Executor ││
│  │  (prices)   │   │  (signals)   │   │  (orders) ││
│  ├────────────┤   ├──────────────┤   ├───────────┤│
│  │  Analyst    │   │ Risk Manager │   │  Monitor  ││
│  │  (TA)       │   │ (sizing/SL)  │   │ (fills)   ││
│  ├────────────┤   └──────────────┘   └───────────┘│
│  │  Sentiment  │                                   │
│  │  (news)     │                                   │
│  └────────────┘                                    │
└────────────────────────────────────────────────────┘
         │                  │                │
    ┌────┴────┐       ┌────┴────┐      ┌────┴────┐
    │  CCXT   │       │ pandas  │      │ SQLite/ │
    │Exchange │       │   -ta   │      │ Postgres│
    └─────────┘       └─────────┘      └─────────┘
```

## Directory Layout

```
src/trading_crew/
├── main.py              Entry point — starts the CrewAI Flow
├── config/              Settings (env + YAML) and CrewAI agent/task definitions
├── models/              Pydantic data models (market, signal, order, portfolio, risk)
├── crews/               CrewAI Crew classes — each wires agents + tasks together
├── agents/              Agent logic — one file per agent role
├── tools/               CrewAI Tools — wrappers around external services
├── strategies/          Trading strategy implementations (pluggable)
├── services/            Infrastructure services (exchange, DB, notifications)
├── risk/                Risk management modules (position sizing, stop-loss, limits)
└── db/                  SQLAlchemy ORM models and Alembic migrations
```

## Data Flow

A single trading cycle follows this path:

```
1. FETCH      Sentinel / MarketIntelligenceService pulls tickers/OHLCV
              from exchanges via CCXT and stores in DB        (Phase 2)
                 ↓
2. ANALYZE    TechnicalAnalyzer computes indicators (EMA, RSI, BB, MACD, ATR)
              and classifies market regime → MarketAnalysis    (Phase 2)
                 ↓
3. SIGNAL     StrategyRunner runs EMA Crossover, Bollinger Bands, RSI Range
              (individual or ensemble) → TradeSignal(s)        (Phase 3)
                 ↓
4. RISK       RiskPipeline validates each signal: confidence filter,
              circuit breaker, position sizing, stop-loss (fixed/ATR),
              portfolio limits, concentration limits → RiskCheckResult
              → OrderRequest if approved                       (Phase 3)
                 ↓
5. EXECUTE    Executor Agent places order (paper or live via CCXT)
                 ↓
6. MONITOR    Monitor Agent tracks order status, detects fills,
              updates portfolio state in DB
                 ↓
7. LOOP       Flow Engine carries state forward → back to step 1
```

Steps 1-4 are deterministic (no LLM required) when `MARKET_PIPELINE_MODE` and
`STRATEGY_PIPELINE_MODE` are set to `deterministic`. The CrewAI agents remain
available in `crewai` or `hybrid` modes for comparison/experimentation.

## Scheduling and Budget Policy

### Independent Crew Schedules

Cost contention mode uses independent intervals per crew:

- Market crew runs on `MARKET_CREW_INTERVAL_SECONDS`
- Strategy crew runs on `STRATEGY_CREW_INTERVAL_SECONDS`
- Execution crew runs on `EXECUTION_CREW_INTERVAL_SECONDS`

These schedules are intentionally decoupled. Strategy is **not** hard-gated by
Market cadence in the scheduler, which allows different tuning profiles without
implicit coupling.

### Daily Token Budget Degrade State Machine

At runtime, budget policy follows a small state machine:

```
NORMAL -> STRATEGY_OFF -> HARD_STOP
```

- `NORMAL`: all crews may run when due.
- `STRATEGY_OFF`: Strategy crew disabled for the rest of UTC day.
- `HARD_STOP`: all LLM crews disabled for the rest of UTC day.

The maximum stage is controlled by `TOKEN_BUDGET_DEGRADE_MODE`:

- `off`: never degrade
- `strategy_only`: cap at `STRATEGY_OFF`
- `hard_stop`: allow full progression to `HARD_STOP`

On UTC day rollover, counters and degrade state reset to `NORMAL`.

### Hard-Stop Monitoring Fallback

In `HARD_STOP`, when `NON_LLM_MONITOR_ON_HARD_STOP=true`, a lightweight non-LLM
probe checks open order statuses via exchange APIs and writes normalized terminal
states back to the database. This preserves basic operational awareness while
token spend is constrained.

## Key Abstractions

### BaseStrategy (strategies/base.py)

All trading strategies implement this interface:

```python
class BaseStrategy(ABC):
    @abstractmethod
    def generate_signal(self, analysis: MarketAnalysis) -> TradeSignal | None:
        """Evaluate market data and return a trade signal, or None."""
```

Community contributors add new strategies by implementing this interface.

### ExchangeService (services/exchange_service.py)

Wraps CCXT to provide a unified, exchange-agnostic API:

```python
class ExchangeService:
    async def fetch_ticker(self, symbol: str) -> Ticker: ...
    async def fetch_ohlcv(self, symbol: str, timeframe: str) -> list[OHLCV]: ...
    async def create_order(self, order: OrderRequest) -> Order: ...
    async def cancel_order(self, order_id: str, symbol: str) -> None: ...
```

### StrategyRunner (services/strategy_runner.py)

Deterministic strategy execution engine that runs all registered strategies
against MarketAnalysis data:

```python
class StrategyRunner:
    def evaluate(self, analyses: dict[str, MarketAnalysis]) -> list[TradeSignal]: ...
```

Supports two modes:
- **Individual**: each strategy runs independently, all actionable signals pass forward
- **Ensemble**: strategies vote per symbol; consensus signal produced only when the
  agreement threshold is met

### RiskPipeline (services/risk_pipeline.py)

Every signal passes through a deterministic risk pipeline before execution:

```
TradeSignal → confidence filter → CircuitBreaker → PositionSizer
→ StopLoss → PortfolioLimits → ConcentrationLimits → RiskCheckResult
```

If any stage rejects the signal, the pipeline short-circuits. Approved signals
produce `OrderRequest` objects ready for the Execution Crew.

Stop-loss can be configured as fixed percentage or ATR-based (adapts to volatility).

## Configuration

Configuration is layered:

1. **Defaults** — hardcoded in `config/settings.py`
2. **YAML** — `config/agents.yaml` and `config/tasks.yaml` for CrewAI definitions
3. **Environment** — `.env` file overrides (secrets, mode, exchange)

Pydantic Settings validates everything at startup.

## Paper vs Live Trading

The `TRADING_MODE` environment variable controls behavior:

- `paper` (default): Orders are simulated locally. No exchange API calls for
  order placement. Safe for development and backtesting.
- `live`: Orders are placed on the real exchange via CCXT. Requires valid API
  credentials and explicit opt-in.
