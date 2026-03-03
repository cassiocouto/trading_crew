# Getting Started

Get Trading Crew running in paper-trading mode in under 5 minutes.

## Prerequisites

- **Python 3.12+**
- **uv** package manager ([install guide](https://docs.astral.sh/uv/getting-started/installation/))
- **Git**

## Installation

```bash
# Clone the repository
git clone https://github.com/your-org/trading-crew.git
cd trading-crew

# Install all dependencies
make dev

# Copy environment template
cp .env.example .env
```

## Configuration

Edit `.env` with your settings. The defaults are safe — paper trading mode
with Binance sandbox and a cost-aware 15-minute loop:

```bash
TRADING_MODE=paper
EXCHANGE_ID=binance
EXCHANGE_SANDBOX=true
LOOP_INTERVAL_SECONDS=900
```

You'll need an OpenAI API key (or local LLM) for the CrewAI agents:

```bash
OPENAI_API_KEY=your-key-here
```

## First Run

```bash
make paper-trade
```

This starts the trading loop in simulation mode. You'll see the agents
fetching data, analyzing indicators, and generating signals — but no real
orders are placed.

## Running Tests

```bash
make test         # All tests
make lint         # Code quality
make type-check   # Type safety
```

## Next Steps

- [Configuration](configuration.md) — Customize symbols, risk params, etc.
- [Writing a Strategy](writing-a-strategy.md) — Add your own trading logic
