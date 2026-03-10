# Trading Crew

> **Deterministic-first crypto trading system with conditional AI advisory**

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-green.svg)](https://www.python.org/)
[![CI](https://img.shields.io/github/actions/workflow/status/cassiocouto/trading_crew/ci.yml?branch=main&label=CI)](https://github.com/cassiocouto/trading_crew/actions/workflows/ci.yml)

---

> **WARNING**: This software is for educational and research purposes only.
> Cryptocurrency trading carries significant risk. Please read the
> [Disclaimer](DISCLAIMER.md) before using this software.

---

## What is Trading Crew?

Trading Crew is an open-source crypto trading system that runs a fully
deterministic pipeline — fetching market data, computing indicators, generating
signals, and managing risk — without any LLM involvement. When market conditions
become uncertain, an optional **advisory crew** (powered by
[CrewAI](https://crewai.com)) activates to review the pipeline output and
recommend adjustments such as vetoing signals, adjusting confidence, or
tightening stop-losses.

### Key Features

- **Deterministic-First Pipeline** — Fetch, analyze, signal, risk-check, and
  execute without LLM calls; AI advisory activates only when needed
- **Uncertainty-Gated Advisory** — An `UncertaintyScorer` computes a [0, 1]
  score from regime, sentiment, strategy disagreement, drawdown, and regime
  change; the advisory crew fires only when the score exceeds a configurable
  threshold
- **Multi-Exchange Support** — Trade on 100+ exchanges via [CCXT](https://github.com/ccxt/ccxt)
  (Binance, NovaDAX, Kraken, Bybit, and more)
- **Risk Management** — Position sizing, stop-loss (fixed or ATR-adaptive),
  portfolio limits, and circuit breakers built in as a first-class concern
- **Paper Trading by Default** — Safe to clone and run; live trading requires
  explicit opt-in
- **Pluggable Strategies** — Add your own trading strategies by implementing a
  simple interface
- **Backtesting** — Validate strategies against historical data before risking
  real capital (see [Backtesting](#backtesting))
- **Real-time Dashboard** — FastAPI + Next.js web UI with WebSocket live updates
  for monitoring portfolio, orders, signals, and agent status (see [Dashboard](#dashboard))

### Demo

<p align="center">
  <img src="docs/demo.gif" alt="Trading Crew dashboard demo" width="800" />
</p>

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

# Copy and configure secrets
cp .env.example .env
# Edit .env — at minimum set OPENAI_API_KEY if you want the advisory crew

# Copy and configure non-secret settings (optional — defaults are sane for paper trading)
cp src/trading_crew/config/settings.yaml.example src/trading_crew/config/settings.yaml
# Edit settings.yaml — or configure everything via the dashboard Settings page
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

Trading Crew uses a **deterministic-first** architecture. The pipeline always
runs without LLM calls:

```
Fetch → Analyze → Signal → Risk Check → [Advisory?] → Execute → Monitor → Loop
                                             │
                          UncertaintyScorer ──┘ (activates advisory only
                                                 when score ≥ threshold)
```

An **advisory crew** of three CrewAI agents (Market Context Advisor, Risk
Advisor, Sentiment Advisor) activates only when the `UncertaintyScorer`
determines conditions are uncertain enough to warrant LLM review. Advisory
adjustments (vetoes, confidence changes, stop-loss tightening) are applied as
directives, then the risk pipeline re-derives order requests.

| Component | Responsibility |
|-----------|----------------|
| **Deterministic Pipeline** | Fetch prices, compute indicators, generate signals, validate risk, execute orders |
| **UncertaintyScorer** | Compute a [0, 1] score from regime, sentiment, disagreement, drawdown, regime change |
| **AdvisoryCrew** | Review pipeline output when uncertainty is high; return adjustment directives |

> **Current status (v0.12.0)**: Full deterministic trading loop with four built-in
> strategies (EMA Crossover, Bollinger Bands, RSI Range, MACD Crossover), circuit
> breakers, stop-loss monitoring, advisory-gated LLM activation, token budget
> degradation, and cycle history persistence. A FastAPI + Next.js dashboard
> provides real-time observability including a Markets page with live candlestick
> chart, signal reasoning sidebar, volatility metrics, and auto-refreshing order
> panels. A self-contained backtesting engine validates strategies against
> historical data.

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
| Markets | Candlestick chart (volume toggleable) per symbol; 1H/4H/1D timeframe; sidebar with **Cycle & Strategies**, **Latest Signals + reasoning**, **Volatility (ATR)**, **Orders**, and **Failed Orders** — all scoped to the selected symbol and auto-refreshing every 15–60 s |
| Orders | Recent orders with status filters, failed orders, per-position P&L cards |
| Signals | Live signal feed with strategy tags and confidence bars |
| History | Equity curve, strategy breakdown table, cycle history |
| Agents | Advisory crew status, uncertainty score, last advisory activation |
| Controls | Live toggles: pause/resume execution agent and advisory crew; advisory is locked when no LLM key is set |
| Backtest | Form to run a backtest over stored OHLCV data and view trade table |
| Settings | Edit all non-secret settings (trading mode, symbols, risk parameters, etc.) via a web form; changes are written to `settings.yaml` |

### WebSocket live updates

The FastAPI server polls the database every 3 seconds and pushes `cycle_complete`, `order_filled`, `signal_generated`, `circuit_breaker`, and `controls_updated` events to connected clients. React Query invalidates the relevant queries on each event so the UI stays current without polling.

### Optional API key

Set `DASHBOARD_API_KEY=<secret>` in your `.env` to require an `X-API-Key` header on all REST requests.

## Configuration

Configuration uses a two-layer model:

| File | Contents | Version-controlled? |
|------|----------|---------------------|
| `.env` | Secrets only: API keys, tokens, `DATABASE_URL` | No (gitignored) |
| `settings.yaml` | All non-secret settings | No (gitignored) |

`settings.yaml.example` and `.env.example` are version-controlled templates.

```bash
cp .env.example .env
cp src/trading_crew/config/settings.yaml.example src/trading_crew/config/settings.yaml
# Edit both files with your values
```

Priority order (highest wins): **environment variables > `.env` > `settings.yaml` > code defaults**

Key settings in `settings.yaml`:

| Setting | Default | Description |
|---------|---------|-------------|
| `trading_mode` | `paper` | `paper` for simulation, `live` for real trading |
| `exchange_id` | `binance` | CCXT exchange identifier |
| `symbols` | `[BTC/USDT]` | Trading pairs to track |
| `loop_interval_seconds` | `900` | Main loop cadence (15m default) |
| `advisory_enabled` | `true` | Enable uncertainty-gated advisory crew |
| `advisory_activation_threshold` | `0.6` | Uncertainty score that triggers advisory |
| `ensemble_enabled` | `true` | Enable ensemble voting across strategies |
| `stop_loss_method` | `fixed` | `fixed` (%) or `atr` (volatility-adaptive) |
| `initial_balance_quote` | `10000` | Starting paper balance (quote currency) |
| `daily_token_budget_tokens` | `600000` | Estimated daily token budget cap |
| `log_level` | `INFO` | Logging verbosity |

Secrets in `.env`:

| Variable | Description |
|----------|-------------|
| `EXCHANGE_API_KEY` / `EXCHANGE_API_SECRET` | Exchange credentials (required for live trading) |
| `OPENAI_API_KEY` | LLM key for the advisory crew |
| `DATABASE_URL` | Database connection string (default: SQLite) |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Optional Telegram alerts |
| `DASHBOARD_API_KEY` | Optional API key to protect the REST dashboard |

See [settings.yaml.example](src/trading_crew/config/settings.yaml.example) and [.env.example](.env.example) for the complete reference.

### LLM Token Costs

LLM tokens are consumed **only when the advisory crew activates** — the
deterministic pipeline uses zero tokens. Advisory activation is driven by the
uncertainty score, so in calm markets with clear signals, many cycles run with
no LLM cost at all.

Use:

- `cost_per_advisory = (input_tokens/1_000_000 * input_price) + (output_tokens/1_000_000 * output_price)`
- `daily_cost = cost_per_advisory * advisory_activations_per_day`

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
