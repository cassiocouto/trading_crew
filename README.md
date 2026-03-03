# Trading Crew

> **Multi-agent crypto trading system powered by CrewAI**

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-green.svg)](https://www.python.org/)
[![CI](https://img.shields.io/github/actions/workflow/status/your-org/trading-crew/ci.yml?label=CI)](https://github.com/your-org/trading-crew/actions)

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
  real capital (coming soon)

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
make lint          # Linter
make type-check    # Type checker
```

## Architecture

Trading Crew is organized into three cooperating **Crews**, each containing
specialized **Agents**:

| Crew | Agents | Responsibility |
|------|--------|----------------|
| **Market Intelligence** | Sentinel, Analyst, Sentiment | Fetch prices, compute indicators, gather signals |
| **Strategy** | Strategist, Risk Manager | Generate trade signals, validate against risk limits |
| **Execution** | Executor, Monitor | Place orders, track fills, manage order lifecycle |

A **CrewAI Flow** orchestrates the crews in a continuous loop:

```
Fetch → Analyze → Signal → Risk Check → Execute → Monitor → Loop
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design document.

## Configuration

All configuration is done through environment variables (`.env` file) and YAML
files. Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `TRADING_MODE` | `paper` | `paper` for simulation, `live` for real trading |
| `EXCHANGE_ID` | `binance` | CCXT exchange identifier |
| `EXCHANGE_SANDBOX` | `true` | Use exchange testnet |
| `DATABASE_URL` | `sqlite:///trading_crew.db` | Database connection string |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

See [.env.example](.env.example) for all available settings.

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
