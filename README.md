# Trading Crew

> **Multi-agent crypto trading system powered by CrewAI**

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-green.svg)](https://www.python.org/)
[![CI](https://img.shields.io/github/actions/workflow/status/cassiocouto/trading_crew/ci.yml?branch=main&label=CI)](https://github.com/cassiocouto/trading_crew/actions/workflows/ci.yml)

---

> **WARNING**: This software is for educational and research purposes only.
> Cryptocurrency trading carries significant risk. Please read the
> [Disclaimer](DISCLAIMER.md) before using this software.

---

## What is Trading Crew?

Trading Crew is an open-source, multi-agent trading system that uses
[CrewAI](https://crewai.com) to orchestrate specialized AI agents for
cryptocurrency trading. Each agent has a distinct role — fetching market data,
analyzing indicators, generating signals, managing risk, or executing trades —
and they collaborate through structured crews.

### Key Features

- **Multi-Agent Architecture** — Specialized agents for data, analysis, strategy,
  risk, and execution, coordinated by CrewAI Flows
- **Multi-Exchange Support** — Trade on 100+ exchanges via [CCXT](https://github.com/ccxt/ccxt)
  (Binance, NovaDAX, Kraken, Bybit, and more)
- **Risk Management** — Position sizing, stop-loss, portfolio limits, and circuit
  breakers built in as a first-class concern
- **Paper Trading by Default** — Safe to clone and run; live trading requires
  explicit opt-in
- **Pluggable Strategies** — Add your own trading strategies by implementing a
  simple interface
- **Backtesting** — Validate strategies against historical data before risking
  real capital (see [Backtesting](#backtesting))
- **Real-time Dashboard** — FastAPI + Next.js web UI with WebSocket live updates
  for monitoring portfolio, orders, signals, and agent status (see [Dashboard](#dashboard))

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Installation

```bash
# Clone the repository
git clone https://github.com/your-org/trading-crew.git
cd trading-crew

# Install dependencies
make dev
# or: uv sync --all-extras

# Copy and configure environment
cp .env.example .env
# Edit .env with your settings (paper trading is the default)
```

### Run in Paper-Trading Mode

```bash
make paper-trade
# or: uv run trading-crew
```

This starts the system in simulation mode — no real orders are placed.

### Run Tests

```bash
make test          # All tests
make test-unit     # Unit tests only
make backtest      # Backtesting tests only
make lint          # Linter
make type-check    # Type checker
```

## Backtesting

Run a historical backtest using locally cached OHLCV data:

```bash
# Fetch data first (saves to local SQLite DB):
make backtest-data

# Run a comparison of all built-in strategies:
make backtest-run

# Or run directly with custom parameters:
python scripts/backtest_runner.py \
  --symbol BTC/USDT --exchange binance --timeframe 1h \
  --from-date 2024-01-01 --to-date 2024-12-31 \
  --fetch --compare --output results.json
```

The engine reuses the same `TechnicalAnalyzer → StrategyRunner → RiskPipeline`
used in live trading. Fills are simulated at next-candle open with configurable
slippage and fees. Metrics include Sharpe ratio, max drawdown, win rate,
profit factor, and total return.

## Architecture

Trading Crew is organized into three cooperating **Crews**, each containing
specialized **Agents**:

| Crew | Agents | Responsibility |
|------|--------|----------------|
| **Market Intelligence** | Sentinel, Analyst, Sentiment | Fetch prices, compute indicators, gather signals |
| **Strategy** | Strategist, Risk Manager | Generate trade signals, validate against risk limits |
| **Execution** | Executor, Monitor | Place orders, track fills, manage order lifecycle |

Each phase adds deterministic (no-LLM) capability alongside the CrewAI agents:

```
Fetch → Analyze → Signal → Risk Check → Execute → Monitor → Loop
  Phase 2 ──────┘          Phase 3 ────┘          Phase 4 (planned)
```

> **Current status (v0.9.0)**: Full trading loop runs as a `TradingFlow`
> CrewAI Flow with circuit breakers, stop-loss monitoring, token budget degradation,
> and cycle history persistence. A self-contained backtesting engine validates
> strategies against historical data. A FastAPI + Next.js dashboard exposes
> real-time observability via WebSocket live updates.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design document.

## Dashboard

The dashboard runs as a separate process alongside the trading loop, reading from the same SQLite database:

```bash
# Install Python + Node dependencies:
make dashboard-install

# Start the FastAPI backend (port 8000):
make dashboard-api

# In a second terminal, start the Next.js UI (port 3000):
make dashboard-ui
```

Open [http://localhost:3000](http://localhost:3000) to view the dashboard.

### Pages

| Page | Content |
|------|---------|
| Overview | Balance, P&L, open positions, last cycle, circuit breaker alert, agent grid |
| Orders | Recent orders with status filters, failed orders, per-position P&L cards |
| Signals | Signal feed with strategy tags and confidence bars |
| History | Equity curve, strategy breakdown table, cycle history |
| Agents | Per-agent pipeline mode, last activity, estimated tokens |
| Backtest | Form to run a backtest over stored OHLCV data and view trade table |

### WebSocket live updates

The FastAPI server polls the database every 3 seconds and pushes `cycle_complete`, `order_filled`, `signal_generated`, and `circuit_breaker` events to connected clients. React Query invalidates the relevant queries on each event so the UI stays current without polling.

### Optional API key

Set `DASHBOARD_API_KEY=<secret>` in your `.env` to require an `X-API-Key` header on all REST requests.

## Configuration

All configuration is done through environment variables (`.env` file) and YAML
files. Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `TRADING_MODE` | `paper` | `paper` for simulation, `live` for real trading |
| `EXCHANGE_ID` | `binance` | CCXT exchange identifier |
| `EXCHANGE_SANDBOX` | `true` | Use exchange testnet |
| `DATABASE_URL` | `sqlite:///trading_crew.db` | Database connection string |
| `LOOP_INTERVAL_SECONDS` | `900` | Main loop cadence (15m default) |
| `MARKET_PIPELINE_MODE` | `deterministic` | Market execution mode |
| `STRATEGY_PIPELINE_MODE` | `deterministic` | Strategy execution mode |
| `ENSEMBLE_ENABLED` | `false` | Enable ensemble voting across strategies |
| `STOP_LOSS_METHOD` | `fixed` | `fixed` (%) or `atr` (volatility-adaptive) |
| `INITIAL_BALANCE_QUOTE` | `10000` | Starting paper balance (quote currency) |
| `COST_CONTENTION_ENABLED` | `true` | Enable cost-aware crew scheduling |
| `DAILY_TOKEN_BUDGET_TOKENS` | `600000` | Estimated daily token budget cap |
| `TOKEN_BUDGET_DEGRADE_MODE` | `strategy_only` | `off`, `strategy_only`, or `hard_stop` |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

See [.env.example](.env.example) for all available settings.

### LLM Token Costs

CrewAI token usage is driven by task execution (not constant idle usage). In the
default 900-second loop, three crews run each cycle (`96` cycles/day), so costs
scale with tokens per cycle and model pricing.

Use:

- `cost_per_cycle = (input_tokens/1_000_000 * input_price) + (output_tokens/1_000_000 * output_price)`
- `daily_cost = cost_per_cycle * (86400 / loop_interval_seconds)`

See [`docs/configuration.md`](docs/docs/configuration.md) for a full estimator
table, daily budget degrade mode, and cost-control strategies.

## Contributing

We welcome contributions! Whether it's a new trading strategy, bug fix, or
documentation improvement, please see [CONTRIBUTING.md](CONTRIBUTING.md) for
guidelines.

### Adding a Strategy

```python
from trading_crew.strategies.base import BaseStrategy
from trading_crew.models.signal import TradeSignal
from trading_crew.models.market import MarketAnalysis

class MyStrategy(BaseStrategy):
    """My custom trading strategy."""

    def generate_signal(self, analysis: MarketAnalysis) -> TradeSignal | None:
        # Your logic here
        ...
```

## Project Status

This project is in **active development** (v0.x). The API may change between
minor versions. See the [CHANGELOG](CHANGELOG.md) for release notes.

## License

[Apache 2.0](LICENSE) — see [DISCLAIMER.md](DISCLAIMER.md) for important legal
notices about using this software for trading.
