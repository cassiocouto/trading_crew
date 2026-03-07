# Architecture

This document explains the high-level design of Trading Crew to help new
contributors navigate the codebase.

## Design Philosophy

Trading Crew follows three core principles:

1. **Safety first** — paper trading by default, risk checks on every signal
2. **Deterministic by default** — the entire pipeline runs without LLM calls;
   AI advisory activates only when market conditions are uncertain
3. **Pluggability** — strategies, exchanges, and notifications are swappable

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                       TradingFlow (CrewAI Flow)                 │
│                    Deterministic-First Pipeline                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌────────────┐              │
│  │   Market     │  │  Strategy   │  │    Risk    │              │
│  │Intelligence  │→ │   Runner    │→ │  Pipeline  │──┐           │
│  │  Service     │  │             │  │            │  │           │
│  └─────────────┘  └─────────────┘  └────────────┘  │           │
│        │                │                           │           │
│        │                │                           │           │
│        │    ┌───────────┴────────────┐              │           │
│        │    │   UncertaintyScorer    │              │           │
│        │    │   (score ≥ threshold?) │              │           │
│        │    └───────────┬────────────┘              │           │
│        │           yes? │ no?                       │           │
│        │    ┌───────────┴────┐                      │           │
│        │    │ AdvisoryCrew   │                      │           │
│        │    │ ┌────────────┐ │ adjust  ┌────────┐   │           │
│        │    │ │  Context   │ │──────→  │Re-run  │   │           │
│        │    │ │  Advisor   │ │         │ Risk   │───┘           │
│        │    │ ├────────────┤ │         │Pipeline│              │
│        │    │ │   Risk     │ │         └────────┘              │
│        │    │ │  Advisor   │ │                                  │
│        │    │ ├────────────┤ │                                  │
│        │    │ │ Sentiment  │ │                                  │
│        │    │ │  Advisor   │ │                                  │
│        │    │ └────────────┘ │                                  │
│        │    └────────────────┘                                  │
│        │                                                        │
│  ┌─────┴───────┐  ┌──────────┐  ┌─────────┐                   │
│  │  Execution  │  │  Stop-   │  │  Cycle  │                   │
│  │  Service    │  │  Loss    │  │ History │                   │
│  │  (orders)   │  │ Monitor  │  │  (DB)   │                   │
│  └─────────────┘  └──────────┘  └─────────┘                   │
└─────────────────────────────────────────────────────────────────┘
         │                                    │
    ┌────┴────┐       ┌─────────┐       ┌────┴────┐
    │  CCXT   │       │ pandas  │       │ SQLite/ │
    │Exchange │       │   -ta   │       │ Postgres│
    └─────────┘       └─────────┘       └─────────┘
```

## Directory Layout

```
src/trading_crew/
├── main.py              Entry point — starts the TradingFlow loop
├── config/              Settings (env + YAML) and CrewAI agent/task definitions
├── models/              Pydantic data models (market, signal, order, portfolio, risk, advisory, cycle)
├── crews/               AdvisoryCrew — condition-triggered advisory crew
├── agents/              Advisory agent factories (context advisor, risk advisor, sentiment advisor)
├── tools/               CrewAI Tools — wrappers around external services
├── strategies/          Trading strategy implementations (pluggable)
├── services/            Infrastructure services (exchange, DB, notifications, uncertainty scorer)
├── risk/                Risk management modules (position sizing, stop-loss, limits)
├── flows/               TradingFlow — deterministic-first cycle orchestration
└── db/                  SQLAlchemy ORM models and Alembic migrations
```

## Data Flow

A single trading cycle follows this path:

```
1. FETCH      MarketIntelligenceService pulls tickers/OHLCV from exchanges
              via CCXT and stores in DB
                 ↓
2. ANALYZE    TechnicalAnalyzer computes indicators (EMA, RSI, BB, MACD, ATR)
              and classifies market regime → MarketAnalysis
                 ↓
3. SIGNAL     StrategyRunner runs EMA Crossover, Bollinger Bands, RSI Range
              (individual or ensemble) → TradeSignal(s)
                 ↓
4. RISK       RiskPipeline validates each signal: confidence filter,
              circuit breaker, position sizing, stop-loss (fixed/ATR),
              portfolio limits, concentration limits → RiskCheckResult
              → OrderRequest if approved
                 ↓
5. ADVISORY   UncertaintyScorer computes a [0,1] uncertainty score.
   (optional)  If score ≥ threshold AND advisory is enabled AND budget allows:
               AdvisoryCrew reviews the pipeline output and returns directives
               (vetoes, confidence adjustments, stop-loss tightening, etc.).
               Adjusted signals are re-run through the RiskPipeline.
                 ↓
6. EXECUTE    ExecutionService places orders (paper or live via CCXT) and
              reconciles open orders
                 ↓
7. MONITOR    Stop-loss monitoring, portfolio snapshots, cycle history
              persisted to DB
                 ↓
8. LOOP       Flow Engine carries state forward → back to step 1
```

Steps 1–4 are always deterministic (no LLM required). Step 5 activates
the advisory crew only when uncertainty is high — most cycles skip it entirely.
Steps 6–8 are deterministic.

## Advisory Activation

The `UncertaintyScorer` combines six weighted factors into a single [0, 1]
score:

| Factor | Weight (default) | Trigger |
|--------|-----------------|---------|
| Volatile regime | 0.3 | Proportion of symbols in `volatile` regime |
| Sentiment extreme | 0.2 | Sentiment score ≥ 0.5 (absolute value) |
| Low sentiment confidence | 0.2 | Sentiment confidence < 0.5 |
| Strategy disagreement | 0.3 | Strategies disagree on direction per symbol |
| Drawdown proximity | 0.2 | Current drawdown as fraction of max allowed |
| Regime change | 0.3 | Symbols whose regime changed since last cycle |

When the score reaches the `ADVISORY_ACTIVATION_THRESHOLD` (default 0.6),
the `AdvisoryCrew` is activated. The crew contains up to three agents:

- **Market Context Advisor** — reviews market data and regime context
- **Risk Advisor** — assesses risk adjustments for the current proposal
- **Sentiment Advisor** — interprets sentiment and news context (optional)

The crew returns `AdvisoryAdjustment` directives:

| Action | Effect |
|--------|--------|
| `veto_signal` | Remove a signal for a specific symbol |
| `adjust_confidence` | Override the signal's confidence value |
| `tighten_stop_loss` | Set a tighter stop-loss percentage |
| `reduce_position_size` | Reduce the position size |
| `sit_out` | Skip all signals for this cycle |

After directives are applied, the risk pipeline re-derives order requests from
the adjusted signals, ensuring portfolio state stays consistent.

## Scheduling and Budget Policy

### Deterministic Loop

The main loop runs on `LOOP_INTERVAL_SECONDS` (default 15 minutes). Every cycle
runs the full deterministic pipeline. The advisory crew only runs when the
uncertainty score triggers it — there are no independent crew schedules.

The `EXECUTION_POLL_INTERVAL_SECONDS` setting controls how often open orders are
reconciled with the exchange. This is decoupled from the main loop interval to
allow independent tuning.

### Daily Token Budget

Token accounting applies **only to advisory crew activations** — the
deterministic pipeline uses zero tokens.

```
NORMAL ──→ BUDGET_STOP
```

- `NORMAL`: advisory crew may activate when uncertainty score triggers it.
- `BUDGET_STOP`: advisory crew is disabled for the rest of the UTC day;
  the deterministic pipeline continues unaffected.

The maximum stage is controlled by `TOKEN_BUDGET_DEGRADE_MODE`:

- `normal`: budget is tracked but never degrades
- `budget_stop`: when projected advisory cost would breach the daily budget,
  advisory is disabled until UTC day rollover

On UTC day rollover, counters and degrade state reset to `NORMAL`.

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
    def evaluate(self, analyses: dict[str, MarketAnalysis]) -> StrategyEvaluation: ...
```

Returns a `StrategyEvaluation` bundling actionable signals with the full
per-strategy vote breakdown (used by the `UncertaintyScorer` to detect
strategy disagreement).

Supports two modes:
- **Individual**: each strategy runs independently, all actionable signals pass forward
- **Ensemble**: strategies vote per symbol; consensus signal produced only when the
  agreement threshold is met

### UncertaintyScorer (services/uncertainty_scorer.py)

Pure deterministic computation — zero LLM cost:

```python
class UncertaintyScorer:
    def score(
        self,
        analyses: dict[str, MarketAnalysis],
        votes: dict[str, list[StrategyVote]],
        portfolio: Portfolio,
        risk_params: RiskParams,
        sentiment: SentimentSnapshot | None = None,
        previous_regimes: dict[str, str] | None = None,
    ) -> UncertaintyResult: ...
```

### AdvisoryCrew (crews/advisory_crew.py)

Condition-triggered CrewAI crew that reviews the deterministic pipeline output:

```python
class AdvisoryCrew:
    async def run(self, context_text: str, uncertainty_score: float) -> AdvisoryResult: ...
```

### RiskPipeline (services/risk_pipeline.py)

Every signal passes through a deterministic risk pipeline before execution:

```
TradeSignal → confidence filter → CircuitBreaker → PositionSizer
→ StopLoss → PortfolioLimits → ConcentrationLimits → RiskCheckResult
```

If any stage rejects the signal, the pipeline short-circuits. Approved signals
produce `OrderRequest` objects. After advisory adjustments, the pipeline re-runs
to re-derive order requests.

Stop-loss can be configured as fixed percentage or ATR-based (adapts to volatility).

## Configuration

Configuration is layered:

1. **Defaults** — hardcoded in `config/settings.py`
2. **YAML** — `config/agents.yaml` and `config/tasks.yaml` for CrewAI advisory definitions
3. **Environment** — `.env` file overrides (secrets, mode, exchange)

Pydantic Settings validates everything at startup.

## Paper vs Live Trading

The `TRADING_MODE` environment variable controls behavior:

- `paper` (default): Orders are simulated locally. No exchange API calls for
  order placement. Safe for development and backtesting.
- `live`: Orders are placed on the real exchange via CCXT. Requires valid API
  credentials and explicit opt-in.

In both modes the pipeline is fully deterministic. The advisory crew, if
enabled, activates identically regardless of trading mode.
