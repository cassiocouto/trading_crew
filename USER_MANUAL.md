# Trading Crew — User Manual

> **Before you read anything else:** This software places real orders on real exchanges when configured to do so. It defaults to paper-trading (simulation) and requires explicit opt-in for live trading. Read [DISCLAIMER.md](DISCLAIMER.md) before using real money. The authors are **NOT** responsible for financial losses.

---

## What is Trading Crew, in plain language?

Trading Crew is a bot that watches cryptocurrency markets, decides when to buy or sell, manages risk, and executes orders — all automatically. It does this by running a set of specialised AI agents in a loop, every 15 minutes by default.

Think of it as a small, automated trading desk:

- One agent **watches the market** (fetches prices, computes technical indicators, classifies the market regime).
- One agent **generates trade signals** (runs strategies like EMA Crossover, Bollinger Bands, RSI Range — or your own).
- One agent **validates risk** (checks position size, stop-losses, portfolio limits, circuit breakers).
- One agent **executes orders** (places them on the exchange or simulates them in paper mode).
- One agent **monitors fills** (tracks order status, updates portfolio balance, detects stale orders).

All of these agents share state through a single trading cycle, coordinated by a [CrewAI](https://crewai.com) Flow. At the end of each cycle the system sleeps, then starts again.

---

## Table of Contents

1. [Quick Start](#1-quick-start)
2. [Paper Trading — Your First Run](#2-paper-trading--your-first-run)
3. [Understanding the Configuration File](#3-understanding-the-configuration-file)
4. [Choosing Your Exchange](#4-choosing-your-exchange)
5. [Understanding Trading Modes](#5-understanding-trading-modes)
6. [The Built-in Strategies](#6-the-built-in-strategies)
7. [Risk Management — How the Bot Protects You](#7-risk-management--how-the-bot-protects-you)
8. [The Dashboard](#8-the-dashboard)
9. [Backtesting](#9-backtesting)
10. [Telegram Notifications](#10-telegram-notifications)
11. [Token Costs and Budget Control](#11-token-costs-and-budget-control)
12. [Going Live — Step by Step](#12-going-live--step-by-step)
13. [Troubleshooting](#13-troubleshooting)
14. [FAQ](#14-faq)

---

## 1. Quick Start

### What you need before starting

- **Python 3.12 or newer** — check with `python --version`
- **[uv](https://docs.astral.sh/uv/getting-started/installation/)** — a fast Python package manager (replaces pip/venv)
- **An OpenAI API key** (or a compatible local LLM) — needed for the CrewAI agents
- An exchange account (Binance, Kraken, Bybit, etc.) — only needed for live trading; paper trading works without one

### Installation

```bash
git clone https://github.com/cassiocouto/trading_crew.git
cd trading_crew

# Install everything
make dev

# Set up your environment file
cp .env.example .env
```

Open `.env` in your editor. The only required change to get started is your OpenAI key:

```
OPENAI_API_KEY=sk-...
```

Everything else can stay at its default for your first run.

---

## 2. Paper Trading — Your First Run

Paper trading is the default. No exchange account is needed. No real money is ever touched. Orders are simulated locally, and portfolio balance is tracked in memory and persisted to the local database.

```bash
make paper-trade
```

You should see log output like this:

```
INFO  [main] Starting Trading Crew v0.8.0 (paper mode)
INFO  [main] --- Cycle 1 ---
INFO  [trading_flow] [1/3] Market Phase: fetching BTC/USDT...
INFO  [trading_flow] Market deterministic pipeline completed. Analyses: 1
INFO  [trading_flow] [2/3] Strategy Phase: evaluating signals...
INFO  [trading_flow] [3/3] Execution Phase: 0 order requests
INFO  [main] Cycle 1 complete. Sleeping 900s
```

The bot will run indefinitely, waking every 15 minutes. Press `Ctrl+C` to stop cleanly — it will finish the current cycle first.

### What to check after your first run

- `trading_crew.log` — full operation log
- `trading_crew.db` — SQLite database with all cycle history, signals, and orders
- Open the dashboard (see Section 8) for a visual overview

---

## 3. Understanding the Configuration File

All settings live in your `.env` file. Here is a tour of the most important ones, grouped by what they do.

### Exchange and trading mode

```env
TRADING_MODE=paper          # "paper" (safe) or "live" (real orders)
EXCHANGE_ID=binance         # Any CCXT exchange ID (binance, kraken, bybit, novadax…)
EXCHANGE_API_KEY=           # Your exchange API key (only needed for live)
EXCHANGE_API_SECRET=        # Your exchange API secret (only needed for live)
EXCHANGE_SANDBOX=true       # Use the exchange's testnet (recommended for testing)
```

### What to trade

```env
SYMBOLS=["BTC/USDT"]        # JSON list of trading pairs, e.g. ["BTC/USDT","ETH/USDT"]
DEFAULT_TIMEFRAME=1h        # Candle timeframe for technical analysis
```

### How often to run

```env
LOOP_INTERVAL_SECONDS=900   # 15 minutes between cycles (default is intentionally slow)
```

Shorter intervals mean more activity and more LLM token cost. 15 minutes is a deliberate default that keeps daily costs manageable (see Section 11).

### Starting balance for paper trading

```env
INITIAL_BALANCE_QUOTE=10000.0   # Simulated starting balance in the quote currency (e.g. USDT)
```

### Notifications

```env
TELEGRAM_BOT_TOKEN=         # Optional: your Telegram bot token
TELEGRAM_CHAT_ID=           # Optional: your Telegram chat ID
```

---

## 4. Choosing Your Exchange

Trading Crew connects to exchanges via [CCXT](https://github.com/ccxt/ccxt), which supports over 100 exchanges. To use a different exchange, simply change `EXCHANGE_ID` in your `.env`:

```env
EXCHANGE_ID=kraken
EXCHANGE_ID=bybit
EXCHANGE_ID=novadax
```

A full list of supported exchange IDs is at [github.com/ccxt/ccxt#supported-cryptocurrency-exchange-markets](https://github.com/ccxt/ccxt#supported-cryptocurrency-exchange-markets).

### Sandbox / testnet

Most major exchanges offer a sandbox environment for testing. With `EXCHANGE_SANDBOX=true`, the bot connects to the testnet and uses test funds. This is a good middle ground between pure paper trading and real live trading — your order logic runs against the real exchange engine, but with fake money.

Note that not all exchanges support sandboxes. If you set `EXCHANGE_SANDBOX=true` on an exchange that doesn't support it, **the bot logs a warning and falls back to production mode**.

---

## 5. Understanding Trading Modes

There are three dimensions of "mode" in Trading Crew. They are independent and can be combined.

### Trading mode (`TRADING_MODE`)

| Value | What happens |
|-------|-------------|
| `paper` | Orders are simulated locally. No exchange calls for order placement. Safe for development. |
| `live` | Orders are placed on the real exchange via CCXT. Requires valid API credentials. |

### Market pipeline mode (`MARKET_PIPELINE_MODE`)

Controls how market data and technical analysis are run.

| Value | What happens |
|-------|-------------|
| `deterministic` | Prices are fetched and indicators computed without any LLM. Fast and cheap. **Default.** |
| `crewai` | The Market Intelligence Crew (AI agents) handles data gathering and analysis. |
| `hybrid` | Both paths run. Useful for comparing AI vs deterministic analysis. |

### Strategy pipeline mode (`STRATEGY_PIPELINE_MODE`)

Controls how trade signals are generated and risk-validated.

| Value | What happens |
|-------|-------------|
| `deterministic` | Built-in strategies (EMA Crossover, Bollinger, RSI) run without LLM. **Default.** |
| `crewai` | The Strategy Crew (AI agents) generates signals. |
| `hybrid` | Both paths run. |

**The practical recommendation:** Start with both pipelines on `deterministic`. This is the most reliable, cheapest, and fastest mode. Once you are comfortable, experiment with `hybrid` to see if the AI agents add value.

---

## 6. The Built-in Strategies

When `STRATEGY_PIPELINE_MODE=deterministic`, Trading Crew runs three strategies simultaneously on each symbol.

### EMA Crossover

Generates a **buy** signal when the fast EMA (12-period) crosses above the slow EMA (50-period) and price is above the fast EMA. Generates a **sell** signal on the reverse. Confidence scales with the spread between the two EMAs.

Best in: trending markets.

### Bollinger Bands

Generates a **buy** signal when price touches or crosses below the lower Bollinger Band (mean-reverting signal). Generates a **sell** signal when price touches the upper band.

Best in: ranging, sideways markets.

### RSI Range

Generates a **buy** signal when RSI(14) is below the oversold threshold (default 35), and a **sell** signal when RSI(14) is above the overbought threshold (default 65). Confidence scales with how far into the extreme zone RSI has moved.

Best in: ranging markets with clear oscillation.

### Running strategies as an ensemble

By default, all three strategies run independently and each can trigger its own order. With ensemble mode enabled, they must agree before any order is placed:

```env
ENSEMBLE_ENABLED=true
ENSEMBLE_AGREEMENT_THRESHOLD=0.6   # 60% of strategies must agree
```

Ensemble mode reduces the number of trades and increases the bar for entry, which can reduce false signals in noisy markets.

---

## 7. Risk Management — How the Bot Protects You

Every signal passes through a deterministic risk pipeline before any order is placed. If any check fails, the signal is rejected and no order is placed. Here is what each check does:

### Minimum confidence filter

Signals below the configured minimum confidence are ignored immediately:

```env
# In the risk settings section of .env / Settings:
# min_confidence = 0.5 (default)
```

### Circuit breaker

If the portfolio drawdown exceeds `max_drawdown_pct` (default 15%), the circuit breaker trips. All trading stops for the rest of the current run until you restart or the drawdown recovers. You will see a red alert in the dashboard and a Telegram notification if configured.

### Position sizing

The bot never allocates more than `max_position_size_pct` (default 10%) of the portfolio into a single position. The exact size is calculated using the `risk_per_trade_pct` (default 2%) formula: the position size is set so that if the stop-loss is hit, you lose at most 2% of your portfolio.

### Stop-loss

Every order request includes a stop-loss price. Two methods are available:

```env
STOP_LOSS_METHOD=fixed     # Stop at a fixed percentage below entry (e.g. 3%)
STOP_LOSS_METHOD=atr       # Stop at ATR(14) * multiplier below entry (adapts to volatility)
ATR_STOP_MULTIPLIER=2.0    # Only applies when using ATR method
```

ATR-based stops are tighter in calm markets and wider in volatile ones, which reduces whipsaw stop-outs.

### Portfolio limits

The risk pipeline enforces:

- `max_portfolio_exposure_pct` (default 80%) — the total portfolio allocated to open positions never exceeds this
- Concentration limits — no single asset can dominate the portfolio disproportionately

### What to do when the circuit breaker trips

1. Check the logs (`trading_crew.log`) and dashboard for the drawdown value
2. If you believe it was a temporary market event, restart the bot — the circuit breaker state is reset on startup
3. If the drawdown reflects real losses, review your strategy settings before restarting
4. Consider widening `max_drawdown_pct` only if you have a specific reason; the default 15% exists to protect you

---

## 8. The Dashboard

The dashboard is a real-time web interface that runs alongside the trading bot, reading from the same database.

### Starting the dashboard

```bash
# Terminal 1 — FastAPI backend (port 8000)
make dashboard-api

# Terminal 2 — Next.js frontend (port 3000)
make dashboard-ui
```

Then open [http://localhost:3000](http://localhost:3000).

Alternatively, run everything with Docker:

```bash
make docker-up
```

### Dashboard pages

| Page | What you'll see |
|------|----------------|
| **Overview** | Current balance, total P&L, open positions, last cycle summary, circuit breaker status, agent activity grid |
| **Orders** | All orders with status filters (open, filled, cancelled, failed). Per-position P&L cards. |
| **Signals** | Live signal feed with strategy tags, signal direction (BUY/SELL), and confidence bars |
| **History** | Equity curve chart, strategy breakdown table (signals generated vs. orders filled), cycle history log |
| **Agents** | Per-agent pipeline mode, last activity timestamp, estimated token usage |
| **Backtest** | Run a backtest over stored historical data directly from the browser |

### Live updates

The dashboard updates automatically via WebSocket. You don't need to refresh — new signals, filled orders, and completed cycles appear within a few seconds.

### Securing the dashboard

If the dashboard is accessible from a network (not just localhost), protect it:

```env
DASHBOARD_API_KEY=your-secret-key
```

Set this in your `.env`. The frontend sends the key automatically; external tools must include the `X-API-Key` header.

---

## 9. Backtesting

Before trusting a strategy with real money, backtest it against historical data.

### Step 1: Fetch historical data

```bash
make backtest-data
```

This downloads OHLCV candles for BTC/USDT (1h timeframe, last 90 days) from Binance and stores them in the local database. You can customise the symbol, exchange, timeframe, and date range:

```bash
uv run python scripts/backtest_runner.py \
  --symbol ETH/USDT \
  --exchange binance \
  --timeframe 4h \
  --from-date 2024-01-01 \
  --to-date 2024-12-31 \
  --fetch --data-only
```

### Step 2: Run a backtest

```bash
make backtest-run
```

Or with custom parameters:

```bash
uv run python scripts/backtest_runner.py \
  --symbol BTC/USDT --exchange binance --timeframe 1h \
  --from-date 2024-01-01 --to-date 2024-12-31 \
  --compare --output results.json
```

`--compare` runs all three built-in strategies side by side and prints a comparison table.

### Reading the results

| Metric | What it means |
|--------|--------------|
| **Total return %** | Overall gain/loss relative to starting balance |
| **Sharpe ratio** | Risk-adjusted return (higher is better; above 1.0 is generally considered decent) |
| **Max drawdown %** | The worst peak-to-trough loss during the period |
| **Win rate %** | Percentage of trades that closed in profit |
| **Profit factor** | Gross profit divided by gross loss (above 1.5 is a reasonable target) |
| **Total trades** | Number of completed round-trips |

### Running backtests from the dashboard

Go to the **Backtest** page in the dashboard, fill in the symbol, timeframe, and date range, and click Run. Results appear in the browser without touching the terminal.

---

## 10. Telegram Notifications

Trading Crew can send you messages when important events happen.

### Setup

1. Create a Telegram bot via [@BotFather](https://t.me/BotFather) and note the token
2. Send any message to your bot, then visit `https://api.telegram.org/bot<TOKEN>/getUpdates` to find your chat ID
3. Add to `.env`:

```env
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id
```

### What triggers notifications

- Order filled
- Order cancelled (stale)
- Circuit breaker tripped
- LLM budget hard stop reached
- System startup and shutdown
- Errors during execution

---

## 11. Token Costs and Budget Control

The AI agents (when using `crewai` or `hybrid` pipeline modes) consume LLM tokens on every crew run. Here is how to understand and control the cost.

### How much does it cost?

It depends on your loop interval and which models you use. As a rough estimate with GPT-4o mini at `LOOP_INTERVAL_SECONDS=900` (96 cycles per day):

| Usage pattern | Tokens/cycle | Daily cost (approx) |
|--------------|-------------|-------------------|
| Light (lean prompts) | ~2,500 | ~$0.06 |
| Typical | ~10,000 | ~$0.23 |
| Heavy (verbose context) | ~25,000 | ~$0.58 |

With `STRATEGY_PIPELINE_MODE=deterministic` and `MARKET_PIPELINE_MODE=deterministic` (the defaults), **no LLM tokens are consumed at all** — the system runs entirely on deterministic logic.

### Budget guards

```env
DAILY_TOKEN_BUDGET_ENABLED=true
DAILY_TOKEN_BUDGET_TOKENS=600000

# What to do when the budget is reached:
# off          — ignore budget (keep running)
# strategy_only — disable Strategy crew for the rest of the UTC day
# hard_stop    — disable ALL LLM crews for the rest of the UTC day
TOKEN_BUDGET_DEGRADE_MODE=strategy_only
```

Budget counters reset at UTC midnight automatically.

### Cost control tips

- **Increase `LOOP_INTERVAL_SECONDS`** — halving cycles halves cost. Try 1800 (30 min) or 3600 (1 hour).
- **Use `deterministic` mode** — no LLM cost at all, still fully functional.
- **Use a cheaper model** — set `OPENAI_MODEL_NAME=gpt-4o-mini` instead of GPT-4.
- **Use a local LLM** — configure `OPENAI_API_BASE` to point at a local Ollama instance.

---

## 12. Going Live — Step by Step

Only do this after you have run paper trading for at least several days and are satisfied with the strategy behaviour.

**Step 1:** Review your risk settings carefully.

```env
RISK__MAX_POSITION_SIZE_PCT=5      # Start conservative — 5% max per position
RISK__MAX_PORTFOLIO_EXPOSURE_PCT=30  # Only 30% of portfolio in positions total
RISK__MAX_DRAWDOWN_PCT=10          # Tight circuit breaker at 10%
RISK__DEFAULT_STOP_LOSS_PCT=2      # 2% stop-loss
```

**Step 2:** Get API credentials from your exchange. Create a key with **trade permissions only** — never give withdrawal permissions to a bot.

**Step 3:** Add your credentials to `.env`:

```env
TRADING_MODE=live
EXCHANGE_ID=binance
EXCHANGE_API_KEY=your-real-key
EXCHANGE_API_SECRET=your-real-secret
EXCHANGE_SANDBOX=false
```

**Step 4:** Start with a small balance. Do not fund the bot with more than you are comfortable losing entirely.

**Step 5:** (Optional) Configure wallet sync. In live mode, the bot reads your real wallet balance from the exchange at startup, and then re-checks it automatically every few minutes. This means if you deposit or withdraw funds externally, the bot will notice and adjust — you do not need to restart it.

```env
BALANCE_SYNC_INTERVAL_SECONDS=300     # Re-check wallet every 5 minutes (0 = disable)
BALANCE_DRIFT_ALERT_THRESHOLD_PCT=1.0 # Get a Telegram alert if balance shifts by 1% or more
```

> **Note:** `INITIAL_BALANCE_QUOTE` is only used for paper trading. In live mode it is completely ignored — the real exchange balance is used instead.

**Step 6:** Start the bot:

```bash
make live-trade
```

You will see a 5-second warning countdown. This is intentional — if you made a config mistake, you can still `Ctrl+C`.

**Step 7:** Monitor closely for the first few hours. Check:
- The dashboard for fills and portfolio changes
- Telegram for fill and error notifications
- `trading_crew.log` for any warnings

---

## 13. Troubleshooting

### The bot starts but immediately stops

Check the logs for a startup error. Common causes:

**"Unknown exchange: xyz"** — The `EXCHANGE_ID` in `.env` is not a valid CCXT exchange ID. Check the [CCXT exchange list](https://github.com/ccxt/ccxt#supported-cryptocurrency-exchange-markets).

**"OPENAI_API_KEY not set"** — CrewAI needs an LLM key even in deterministic mode (for agent definitions). Set `OPENAI_API_KEY` in `.env`.

**"Database error at startup"** — The SQLite file may be locked or corrupted. Try deleting `trading_crew.db` and restarting (you will lose history).

---

### The bot runs but never places orders

This is normal at first — the strategies may not be generating signals above the confidence threshold. Check:

1. **Signals page in the dashboard** — are signals being generated at all? If not, the strategies are not finding entry conditions.
2. **Log output during the strategy phase** — look for lines mentioning "confidence" or "risk check rejected"
3. **Circuit breaker** — if `circuit_breaker_tripped: True` appears in the overview page, the bot has halted trading
4. **Balance too low** — in paper mode, check `INITIAL_BALANCE_QUOTE`; in live mode the bot reads the real wallet balance at startup, so check your actual exchange balance. If the balance is too low relative to the minimum order size on your exchange, the position sizer will produce zero-size orders.

---

### "SQLITE_BUSY" or database errors

The dashboard and trading bot both access the database. Normally the WAL mode prevents conflicts, but on slow machines you may see busy errors. Try:

```env
# In settings (advanced): increase the busy timeout
DATABASE_BUSY_TIMEOUT_MS=10000
```

If using Docker, make sure the `./data` volume is mounted correctly.

---

### Orders placed in paper mode but balance not updating

Paper-trading balance is tracked in memory and only written to the database at the end of each cycle. If you kill the bot mid-cycle with `Ctrl+C`, the last cycle's changes may not be persisted. This is expected — paper trading is not meant to be perfectly durable.

---

### The circuit breaker tripped and won't reset

The circuit breaker resets on bot restart. It does **not** reset automatically during a run, even if the market recovers. This is by design — a trip indicates something went wrong and human review is appropriate.

```bash
# Stop the bot
Ctrl+C

# Review the logs
cat trading_crew.log | grep "circuit_breaker"

# Restart when ready
make paper-trade
```

---

### High LLM token costs

See Section 11. The fastest fix is to switch to `deterministic` pipeline mode:

```env
MARKET_PIPELINE_MODE=deterministic
STRATEGY_PIPELINE_MODE=deterministic
```

This eliminates all LLM token usage while keeping the full trading loop running.

---

### Dashboard shows "WebSocket disconnected"

The dashboard backend (`make dashboard-api`) needs to be running. Check that port 8000 is not blocked. If running with Docker, ensure both services started with `make docker-up`.

---

## 14. FAQ

**Q: Does the bot make money?**

**We don't know and won't claim it does.** The included strategies are educational implementations of common technical analysis methods. Past backtest performance does not guarantee future live results. Always paper-trade first and treat this as a research tool, not an income source.

---

**Q: Can I run multiple symbols at once?**

Yes:

```env
SYMBOLS=["BTC/USDT","ETH/USDT","SOL/USDT"]
```

Each symbol is analysed independently each cycle. Risk limits apply to the portfolio as a whole.

---

**Q: How do I stop the bot cleanly?**

Press `Ctrl+C`. The bot will finish the current cycle, write results to the database, and exit. Killing it forcefully (e.g. `kill -9`) may cause the last cycle to be partially persisted.

---

**Q: Can I run Trading Crew 24/7 on a server?**

Yes. Use Docker:

```bash
make docker-up
```

The `trading-bot` service restarts automatically if it crashes (`restart: unless-stopped` in `docker-compose.yml`). Logs are available via `docker compose logs -f trading-bot`.

---

**Q: What happens to open orders when I stop the bot?**

Open orders remain on the exchange. When you restart, the bot will detect them on the next Monitor phase and update their status. In paper mode, open orders are tracked in the database and picked up on restart.

---

**Q: Is my API key safe?**

Your API key is stored only in `.env` locally and is never sent anywhere except the exchange API. Do not commit `.env` to version control. A `.gitignore` rule already excludes it. For live trading, create an API key with **trade permissions only** — never grant withdrawal permissions.

---

**Q: I want to use a different LLM (not OpenAI). Can I?**

Yes. CrewAI supports any OpenAI-compatible endpoint. For a local Ollama model:

```env
OPENAI_API_BASE=http://localhost:11434/v1
OPENAI_MODEL_NAME=llama3
OPENAI_API_KEY=ollama   # Ollama ignores this but CrewAI requires it to be set
```

---

**Q: The backtest results look great. Can I trust them?**

Backtest results should be treated with healthy scepticism. Common pitfalls:

- **Overfitting** — a strategy tuned on historical data may not generalise
- **Lookahead bias** — the backtester uses strict forward-only logic, but always verify this for any strategy you add
- **Execution assumptions** — the backtester fills at next-candle open with configurable slippage; real fills differ
- **Small sample sizes** — a 90-day backtest with 20 trades is statistically weak

Use backtests to rule out obviously bad strategies, not to guarantee future profit.

---

*For developer documentation, see [DEVELOPER_MANUAL.md](DEVELOPER_MANUAL.md).*
*For the full configuration reference, see [docs/docs/configuration.md](docs/docs/configuration.md).*
*For architecture details, see [ARCHITECTURE.md](ARCHITECTURE.md).*
