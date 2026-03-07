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
with Binance sandbox and a 15-minute deterministic loop:

```bash
TRADING_MODE=paper
EXCHANGE_ID=binance
EXCHANGE_SANDBOX=true
LOOP_INTERVAL_SECONDS=900
```

An LLM API key is **optional**. The deterministic pipeline runs without one.
If you want the advisory crew to activate when uncertainty is high, set:

```bash
OPENAI_API_KEY=your-key-here
ADVISORY_ENABLED=true
```

Without an API key, set `ADVISORY_ENABLED=false` and the system operates in
fully deterministic mode with no LLM involvement.

## First Run

```bash
make paper-trade
```

This starts the trading loop in simulation mode. You'll see the deterministic
pipeline fetching data, computing indicators, generating signals, and running
risk checks — all without LLM calls. If the uncertainty score exceeds the
threshold and advisory is enabled, the advisory crew will activate for that
cycle. No real orders are placed.

## Running Tests

```bash
make test         # All tests
make lint         # Code quality
make type-check   # Type safety
```

## Next Steps

- [Configuration](configuration.md) — Customize symbols, risk params, advisory threshold, etc.
- [Writing a Strategy](writing-a-strategy.md) — Add your own trading logic
