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
1. FETCH      Sentinel Agent pulls tickers/OHLCV from exchanges via CCXT
                 ↓
2. ANALYZE    Analyst Agent computes indicators (EMA, RSI, Bollinger, etc.)
                 ↓
3. SIGNAL     Strategist Agent runs strategies → produces TradeSignal(s)
                 ↓
4. RISK       Risk Manager validates signal against portfolio limits,
              calculates position size, sets stop-loss
                 ↓
5. EXECUTE    Executor Agent places order (paper or live via CCXT)
                 ↓
6. MONITOR    Monitor Agent tracks order status, detects fills,
              updates portfolio state in DB
                 ↓
7. LOOP       Flow Engine carries state forward → back to step 1
```

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

### Risk Pipeline (risk/)

Every signal passes through a risk pipeline before execution:

```
TradeSignal → PositionSizer → StopLoss → PortfolioLimits → CircuitBreaker → OrderRequest
```

If any stage rejects the signal, the order is not placed.

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
