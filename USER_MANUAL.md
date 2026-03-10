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

# Set up secrets
cp .env.example .env
# Open .env — the only required change for your first run is your OpenAI key:
#   OPENAI_API_KEY=sk-...

# Set up non-secret settings (optional — defaults are fine for paper trading)
cp src/trading_crew/config/settings.yaml.example src/trading_crew/config/settings.yaml
```

Everything can stay at its default for your first run. The only thing you must fill in is your OpenAI key in `.env`.

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

## 3. Understanding the Configuration Files

Configuration uses a two-layer model. **Secrets** stay in `.env`. **Everything else** lives in `settings.yaml`.

| File | What goes here | Version-controlled? |
|------|---------------|---------------------|
| `.env` | API keys, tokens, `DATABASE_URL` | No (gitignored) |
| `settings.yaml` | All non-secret settings | No (gitignored) |

Both files have committed example templates: `.env.example` and `settings.yaml.example`.

### Secrets (`.env`)

```env
EXCHANGE_API_KEY=           # Your exchange API key (only needed for live trading)
EXCHANGE_API_SECRET=        # Your exchange API secret (only needed for live trading)
DATABASE_URL=sqlite:///trading_crew.db   # Connection string
OPENAI_API_KEY=sk-...       # Required for the advisory crew
# TELEGRAM_BOT_TOKEN=       # Optional notifications
# TELEGRAM_CHAT_ID=
# DASHBOARD_API_KEY=        # Optional: protect the REST API with a key
```

### Non-secret settings (`settings.yaml`)

Open `settings.yaml` to configure how the bot behaves. Here are the most important settings:

```yaml
# Trading mode: "paper" (safe, default) or "live" (real orders)
trading_mode: "paper"

# Exchange
exchange_id: "binance"        # Any CCXT exchange ID
exchange_sandbox: false       # true = use the exchange testnet

# What to trade
symbols:
  - "BTC/USDT"
  # - "ETH/USDT"             # add more pairs here
default_timeframe: "1h"       # Candle timeframe for technical analysis

# How often to run
loop_interval_seconds: 900    # 15 minutes (default, intentionally slow)
```

Shorter loop intervals mean more activity and more LLM token cost when the advisory crew is active. 15 minutes keeps daily costs manageable (see Section 11).

```yaml
# Starting balance for paper trading only
# (ignored in live mode — the real exchange balance is used)
initial_balance_quote: 10000.0
```

### The Settings page

All non-secret settings can also be edited directly from the dashboard **Settings page** at [http://localhost:3000/settings](http://localhost:3000/settings) — no need to touch `settings.yaml` by hand. Changes take effect on the next bot restart (most settings) or immediately via the Controls page (execution and advisory toggles).

### Priority order

If you set a value in an environment variable or in `.env`, it takes priority over `settings.yaml`:

```
environment variables  >  .env  >  settings.yaml  >  built-in defaults
```

This means you can always override a setting temporarily via an environment variable without editing any file.

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

There are two independent dimensions of "mode" in Trading Crew.

### Trading mode (`trading_mode` in `settings.yaml`)

| Value | What happens |
|-------|-------------|
| `paper` | Orders are simulated locally. No exchange calls for order placement. Safe for development. **Default.** |
| `live` | Orders are placed on the real exchange via CCXT. Requires valid API credentials. |

### Advisory mode

The advisory crew is a set of AI agents (powered by CrewAI) that activates **only when market conditions are uncertain**. The rest of the time — clear trends, low volatility, confident strategy signals — the bot runs entirely on deterministic logic with zero LLM calls.

The advisory crew activates when the `UncertaintyScorer` computes a score above `advisory_activation_threshold` (default 0.6). You can observe activations on the **Agents** page in the dashboard.

| Setting | Default | What it controls |
|---------|---------|-----------------|
| `advisory_enabled` | `true` | Whether the advisory crew can activate at all |
| `advisory_activation_threshold` | `0.6` | Uncertainty score required to trigger the crew |

The advisory crew requires an OpenAI API key (or compatible LLM). If none is configured, it is automatically disabled and the bot runs in fully deterministic mode.

**The practical recommendation:** Keep the defaults. The deterministic pipeline handles the vast majority of cycles. The advisory crew adds a human-like sanity check only when conditions are ambiguous.

### How the uncertainty score is calculated

Every cycle the bot computes a single number — the **uncertainty score** (0.0–1.0) — from six independent factors. If the score equals or exceeds `advisory_activation_threshold` the advisory crew is invoked; otherwise the cycle completes without any LLM calls.

**The formula:**

```
score = clamp(
    factor_volatile_regime     × weight_volatile_regime
  + factor_sentiment_extreme   × weight_sentiment_extreme
  + factor_low_confidence      × weight_low_sentiment_confidence
  + factor_disagreement        × weight_strategy_disagreement
  + factor_drawdown_proximity  × weight_drawdown_proximity
  + factor_regime_change       × weight_regime_change
, min=0.0, max=1.0)
```

Each factor produces a value between 0 and 1. It is multiplied by its configurable weight and the results are summed. The sum is **clamped to [0, 1]**. The six factors:

| Factor | What it measures | Raw value |
|--------|-----------------|-----------|
| **Volatile Regime** | Fraction of tracked symbols currently classified as "volatile" (ATR/price exceeds `market_regime_volatility_threshold`) | 0 = none volatile, 1 = all volatile |
| **Sentiment Extreme** | Whether the market sentiment score is at an extreme — triggers when `|sentiment_score| ≥ 0.5` (very fearful or very greedy) | 0 or 1 (binary) |
| **Low Sentiment Confidence** | Whether confidence in the sentiment reading is low — triggers when `1 − confidence ≥ 0.5` | 0 or 1 (binary) |
| **Strategy Disagreement** | Average cross-strategy disagreement per symbol — how evenly split buy/sell/hold votes are | 0 = full consensus, 1 = perfectly split |
| **Drawdown Proximity** | How close the portfolio is to the circuit-breaker: `current_drawdown / max_drawdown_pct` | 0 = no drawdown, 1 = at the limit |
| **Regime Change** | Fraction of symbols that changed market regime (e.g. trending → ranging) since the previous cycle | 0 = no change, 1 = all changed |

**Why the weights sum to 1.5 (not 1.0):** This is intentional. When multiple factors fire simultaneously the score climbs more aggressively toward 1.0, making advisory activation more likely in compounding uncertainty situations. A single factor at its maximum can contribute at most its own weight (0.2–0.3), which is below the default threshold of 0.6 — so one factor alone is not enough to trigger the advisory crew. Two or three factors firing together typically push the score past the threshold.

**Example:** In a volatile market where strategies disagree:
- Volatile regime = 1.0 × 0.3 = **0.30**
- Strategy disagreement = 0.8 × 0.3 = **0.24**
- Regime change = 0.5 × 0.3 = **0.15**
- Others = 0
- **Total = 0.69 → advisory activates** (threshold 0.6)

**Tuning the score:**
- To reduce advisory frequency, **raise `advisory_activation_threshold`** (e.g. 0.75) or **lower individual weights** for factors that matter less to your strategy.
- To make advisory fire more aggressively, lower the threshold or raise weights for factors you consider most important.
- Setting a factor's weight to `0.0` disables that factor entirely.
- The sentiment factors (`sentiment_extreme`, `low_sentiment_confidence`) produce zero contribution when `sentiment_enabled: false` — no need to zero out their weights.

### Advisory crew lifecycle — active, idle, and back again

**The advisory crew has no persistent "active" state.** It is invoked at most once per cycle, on-demand, and is otherwise completely idle. Understanding this makes it much easier to reason about frequency and cost.

```
Each cycle (every loop_interval_seconds, default 15 min):
  ┌─ Deterministic pipeline runs (always)
  │    market data → strategies → signals → risk evaluation
  │
  ├─ Uncertainty score is computed (always, zero LLM cost)
  │
  ├─ score < threshold  →  advisory crew is SKIPPED  (idle this cycle)
  │
  └─ score ≥ threshold  →  advisory crew RUNS once, then stops
         AI agents review signals, optionally adjust them, done.
         Next cycle starts fresh — score is recomputed from scratch.
```

**How often can it run?** At most once per `loop_interval_seconds`. With the default 15-minute interval, the theoretical maximum is 96 advisory activations per day. In practice, consecutive cycles in calm markets will keep the score below the threshold and the crew will not run at all.

**What makes it "go back to idle"?** Nothing explicit needs to happen — the crew is always idle unless the current cycle's score reaches the threshold. Once market conditions normalise (volatility drops, strategies agree, drawdown recovers, no regime change), the score falls back below the threshold automatically on the next cycle and the crew is skipped again.

**Additional conditions that prevent the crew from running**, even when the score is high enough:

| Condition | Where to change it |
|-----------|-------------------|
| `advisory_enabled: false` in settings | Settings page → Advisory Crew section |
| Advisory paused via dashboard | Controls page → Advisory toggle |
| No OpenAI API key in `.env` | `.env` file — `OPENAI_API_KEY` |
| Daily token budget exhausted (`budget_stop` mode) | Resets automatically at midnight UTC; or raise the budget limit |

**The advisory crew never blocks the next cycle.** If the crew fails for any reason (network error, LLM timeout), the bot logs the error, proceeds with the original deterministic signals, and the next cycle starts normally.

---

## 6. The Built-in Strategies

Trading Crew runs four strategies simultaneously on each symbol every cycle.

### EMA Crossover

Generates a **buy** signal when the fast EMA (12-period) crosses above the slow EMA (50-period) and price is above the fast EMA. Generates a **sell** signal on the reverse. Confidence scales with the spread between the two EMAs.

Best in: trending markets. Fires infrequently — only when an actual crossover event occurs.

### Bollinger Bands

Generates a **buy** signal when price is within 10% of the lower Bollinger Band width from the lower edge, and a **sell** signal when price approaches the upper band. Confidence scales with how close the price is to (or beyond) the band. The 10% proximity window means the strategy fires before price reaches the exact band edge, making it more responsive to mean-reversion setups.

Best in: ranging, sideways markets.

### RSI Range

Generates a **buy** signal when RSI(14) is below the oversold threshold (default 35) *and* price is in the bottom 20% of the recent price range. Generates a **sell** signal when RSI is above 65 and price is in the top 20% of the range. Both conditions must be true simultaneously. Confidence scales with how far RSI has moved into the extreme zone.

Best in: ranging markets with clear oscillation.

### MACD Crossover

Generates a **buy** signal when the MACD histogram is positive (MACD line above its signal line) and a **sell** signal when it is negative. Fires on practically every cycle in a trending or volatile market, making it the most active of the four built-in strategies. Confidence scales with the size of the histogram relative to the current price — larger separations produce higher-confidence signals.

Best in: trending markets; also active in volatile regimes. Can produce frequent signals in choppy conditions — consider enabling ensemble mode to require agreement from other strategies.

### Running strategies as an ensemble

By default, all four strategies run independently and each can trigger its own order. With ensemble mode enabled, they must agree before any order is placed:

```env
ENSEMBLE_ENABLED=true
ENSEMBLE_AGREEMENT_THRESHOLD=0.6   # 60% of strategies must agree
```

Ensemble mode reduces the number of trades and increases the bar for entry, which can reduce false signals in noisy markets. With four strategies and a 60% threshold, at least 3 out of 4 must agree.

---

## 7. Risk Management — How the Bot Protects You

Every signal passes through a deterministic risk pipeline before any order is placed. If any check fails, the signal is rejected and no order is placed. Here is what each check does:

### Minimum confidence filter

Signals below the configured minimum confidence are ignored immediately:

```yaml
# In settings.yaml (under the risk: section):
risk:
  min_confidence: 0.5   # default
```

### Circuit breaker

If the portfolio drawdown exceeds `max_drawdown_pct` (default 15%), the circuit breaker trips. All trading stops for the rest of the current run until you restart or the drawdown recovers. You will see a red alert in the dashboard and a Telegram notification if configured.

### Position sizing

The bot never allocates more than `max_position_size_pct` (default 10%) of the portfolio into a single position. The exact size is calculated using the `risk_per_trade_pct` (default 2%) formula: the position size is set so that if the stop-loss is hit, you lose at most 2% of your portfolio.

### Stop-loss

Every order request includes a stop-loss price. Two methods are available:

```yaml
# In settings.yaml:
stop_loss_method: "fixed"    # "fixed" = fixed % below entry; "atr" = ATR-adaptive
atr_stop_multiplier: 2.0     # only applies when stop_loss_method is "atr"
```

ATR-based stops are tighter in calm markets and wider in volatile ones, which reduces whipsaw stop-outs.

### Portfolio limits

The risk pipeline enforces:

- `max_portfolio_exposure_pct` (default 80%) — the total portfolio allocated to open positions never exceeds this
- Concentration limits — no single asset can dominate the portfolio disproportionately

### Anti-averaging-down guard

When this guard is on (the default), the bot refuses to buy more of an asset once the market has fallen *past your stop-loss floor*.

**In plain terms:** Imagine you bought BTC at $100K with a stop-loss at $97K. The market drops to $95K and a new buy signal fires. The guard sees that $95K is below your $97K stop and rejects the signal — you are not throwing good money after bad while the position is already at risk. If the market drops further and the stop-loss triggers, the position closes normally. The next time you buy BTC (fresh start, no open position), the guard resets and the new buy sets a new bar.

```yaml
# In settings.yaml:
anti_averaging_down: true    # default; set to false to disable
```

**The threshold is your stop-loss.** You control how aggressive it is by adjusting `STOP_LOSS_METHOD` and `STOP_LOSS_PCT`. A wider stop gives more room before the guard activates; a tighter stop is more conservative.

### Break-even sell guard

When this guard is on (the default), the bot will not sell a position at a loss relative to what you actually paid — including fees and slippage.

**In plain terms:** Imagine you bought BTC twice: Lot 1 at $100K (fees included → break-even $100.1K) and Lot 2 at $90K (break-even $90.09K). A sell signal fires at $89K. The guard checks: is $89K above the break-even of your most recent buy? No ($89K < $90.09K). So it holds — no sell. If the market recovers to $93K, the guard approves ($93K > $90.09K) and the sell goes through.

This is intentional — **the bot prefers to hold rather than sell at a confirmed loss**. Stop-loss exits are not affected; those bypass this guard entirely and fire regardless of break-even.

```yaml
# In settings.yaml:
sell_guard_mode: "break_even"   # default; set to "none" to disable
risk:
  min_profit_margin_pct: 0.0    # set e.g. 1.0 to require 1% profit above break-even
```

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
| **Markets** | Candlestick chart (volume toggleable via checkbox) per tracked symbol; 15M/1H/4H/1D timeframe selector; right-hand sidebar with five collapsible panels — **Cycle & Strategies** (current cycle number + per-strategy buy/sell signal counts), **Latest Signals** (most recent signals with confidence, risk verdict, and full strategy reasoning — click to expand), **Volatility** (ATR(14), ATR%, 20-bar price range), **Orders**, and **Failed Orders** — all scoped to the selected symbol and auto-refreshing. |
| **Orders** | All orders with status filters (open, filled, cancelled, failed). Per-position P&L cards. |
| **Signals** | Live signal feed with strategy tags, signal direction (BUY/SELL), and confidence bars |
| **History** | Equity curve chart, strategy breakdown table (signals generated vs. orders filled), cycle history log |
| **Agents** | Per-agent pipeline mode, last activity timestamp, estimated token usage |
| **Controls** | Live toggles to pause/resume the execution agent and advisory crew without restarting the bot |
| **Backtest** | Run a backtest over stored historical data directly from the browser |
| **Settings** | View and edit all non-secret settings via a web form; saves to `settings.yaml` |

### Dark mode

The dashboard supports Light, Dark, and System themes. Click the theme toggle at the bottom of the sidebar to cycle between modes. Your preference is saved in the browser and persists across sessions. When set to System, the dashboard follows your operating system's light/dark preference automatically.

### Live updates

The dashboard uses a WebSocket push model for real-time updates. The API server polls the database every few seconds (controlled by `dashboard_ws_poll_interval_seconds` in `settings.yaml`, default 3 s) and pushes events to all connected browsers:

| Event | Trigger | What refreshes |
|-------|---------|----------------|
| `cycle_complete` | Bot finishes a trading cycle | Portfolio, P&L history, cycle counter |
| `order_filled` | An order is filled on the exchange | Orders list, portfolio balance |
| `signal_generated` | A strategy emits a new signal | Signals feed, strategy stats |
| `market_data_updated` | Bot writes fresh ticker/OHLCV data | Chart candles, ticker prices, signals, orders |
| `circuit_breaker` | Circuit breaker trips | System status |

On the Markets page, chart data, ticker prices, signals, and orders all refresh **instantly** when the bot completes a cycle — no manual reload needed. A 30-second fallback poll runs as a safety net in case the WebSocket disconnects. The status bar in the page header shows elapsed time since the last data fetch and pulses while a background refresh is in progress.

### Live controls

The **Controls** page lets you pause and resume the execution agent and advisory crew without restarting the bot. Changes take effect within one cycle interval (15 minutes by default). Use this to temporarily disable trading while you review a market situation, or to disable the advisory crew if you want to reduce LLM costs for a period.

The advisory toggle is locked if no valid OpenAI API key is configured.

### Securing the dashboard

If the dashboard is accessible from a network (not just localhost), protect it by setting this in `.env`:

```env
DASHBOARD_API_KEY=your-secret-key
```

The frontend sends the key automatically; external tools must include the `X-API-Key` header.

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

Go to the **Backtest** page in the dashboard, fill in the symbol, timeframe, and date range, and click Run. Results appear in the browser without touching the terminal. Enable the **Full Simulation** checkbox to run the real `TradingFlow` against the data instead of the fast legacy backtest.

### Full simulation mode

The legacy backtest is fast but simplified -- it reimplements strategy/risk logic in isolation and skips circuit-breaker halting, break-even sell guards, and the full CrewAI Flow graph. **Full simulation mode** runs the actual `TradingFlow` per candle against a simulated exchange and in-memory database, so results reflect how the live system actually behaves.

```bash
uv run python scripts/backtest_runner.py \
  --simulation \
  --candles-file data/BTCUSDT-1m.csv \
  --resample 1h \
  --from-date 2024-01-01 \
  --to-date 2024-12-31
```

Key flags:

| Flag | Description |
|------|-------------|
| `--simulation` | Use full `TradingFlow` simulation instead of legacy backtest |
| `--candles-file PATH` | Load candles from a CSV file (Binance kline format) instead of the database |
| `--resample TIMEFRAME` | Aggregate CSV candles to a larger timeframe (e.g. `1h`, `4h`, `1d`) |
| `--max-bars N` | Safety valve: cap bars processed (default: 50,000) |

The simulation supports the same `--compare`, `--output`, and `--advisory-mode` flags as the legacy backtest.

**Known limitations:**
- Single symbol per run (same as legacy backtest)
- Sentiment data is not available in simulation (scores zero)
- Orders fill immediately at candle close +/- slippage (no next-bar-open fills)
- Slower than legacy backtest due to full Flow instantiation per bar; use `--resample` to reduce bar count

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

The **advisory crew** is the only component that consumes LLM tokens. It activates only when the `UncertaintyScorer` determines that conditions are ambiguous enough to warrant AI review. In calm, trending markets the advisory crew may never activate — meaning many cycles run with zero token cost.

### How much does it cost?

It depends on your loop interval, how often the advisory activates, and which model you use. As a rough estimate with GPT-4o mini at `loop_interval_seconds: 900` (96 cycles per day) and advisory activating on 20% of cycles:

| Advisory activations/day | Tokens/cycle | Daily cost (approx) |
|--------------------------|-------------|-------------------|
| ~5 (rare activation) | ~4,000 | ~$0.01 |
| ~20 (typical) | ~4,000 | ~$0.05 |
| ~96 (every cycle) | ~4,000 | ~$0.23 |

If `advisory_enabled: false` in `settings.yaml`, or if no OpenAI API key is set, **no LLM tokens are consumed at all** — the system runs entirely on deterministic logic.

### Budget guards

```yaml
# In settings.yaml:
daily_token_budget_enabled: true
daily_token_budget_tokens: 600000

# What to do when the budget is reached:
# "normal"      — disable advisory crew for the rest of the UTC day, keep everything else
# "budget_stop" — disable ALL LLM usage for the rest of the UTC day
token_budget_degrade_mode: "normal"
```

Budget counters reset at UTC midnight automatically.

### Cost control tips

- **Increase `loop_interval_seconds`** — halving cycles halves advisory activation frequency. Try 1800 (30 min) or 3600 (1 hour).
- **Raise `advisory_activation_threshold`** — a higher threshold (e.g. 0.75) means the advisory crew fires less often.
- **Disable advisory entirely** — set `advisory_enabled: false` for zero LLM cost; the deterministic pipeline is fully functional on its own.
- **Use a cheaper model** — set `OPENAI_MODEL_NAME=gpt-4o-mini` in `.env` instead of GPT-4.
- **Use a local LLM** — configure `OPENAI_API_BASE` to point at a local Ollama instance.

---

## 12. Going Live — Step by Step

Only do this after you have run paper trading for at least several days and are satisfied with the strategy behaviour.

**Step 1:** Review your risk settings carefully. Edit `settings.yaml`:

```yaml
# Start conservative — tighten these before going live
risk:
  max_position_size_pct: 5        # 5% max per position (default is 10%)
  max_portfolio_exposure_pct: 30  # Only 30% of portfolio in positions total
  max_drawdown_pct: 10            # Circuit breaker at 10% (default is 15%)
  default_stop_loss_pct: 2        # 2% stop-loss
```

**Step 2:** Get API credentials from your exchange. Create a key with **trade permissions only** — never give withdrawal permissions to a bot.

**Step 3:** Add your credentials to `.env` and switch the trading mode in `settings.yaml`:

In `.env`:
```env
EXCHANGE_API_KEY=your-real-key
EXCHANGE_API_SECRET=your-real-secret
```

In `settings.yaml`:
```yaml
trading_mode: "live"
exchange_id: "binance"
exchange_sandbox: false
```

**Step 4:** Start with a small balance. Do not fund the bot with more than you are comfortable losing entirely.

**Step 5:** (Optional) Configure wallet sync in `settings.yaml`. In live mode, the bot reads your real wallet balance from the exchange at startup, and then re-checks it automatically every few minutes. This means if you deposit or withdraw funds externally, the bot will notice and adjust — you do not need to restart it.

```yaml
balance_sync_interval_seconds: 300     # Re-check wallet every 5 minutes (0 = disable)
balance_drift_alert_threshold_pct: 1.0 # Telegram alert if balance shifts by 1% or more
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

This is normal at first — the strategies generate signals only when their specific conditions are met:

- **MACD Crossover** fires on most cycles and should produce signals quickly.
- **EMA Crossover** fires only when price crosses above or below the fast EMA — infrequent in a sideways market.
- **Bollinger Bands** fires when price is within 10% of band width from either edge.
- **RSI Range** fires only when RSI is below 35 *and* price is in the bottom 20% of the recent range — a stricter combined condition that may not trigger for many cycles in a neutral market.

If you have been running for several cycles and still see zero signals, check:

1. **Markets page sidebar → Latest Signals** — if it shows no signals, the strategies are not finding entry conditions for this symbol/timeframe. Try a different timeframe (4H or 1D) which may show more signal history.
2. **Log output during the strategy phase** — look for `Strategy pipeline: 0 signals`; if you see it consistently, the conditions above are genuinely not met.
3. **Signals page in the dashboard** — filter by strategy to see whether any single strategy is producing signals.
4. **Log output mentioning "confidence" or "risk check rejected"** — signals may be generated but filtered downstream.
5. **Circuit breaker** — if `circuit_breaker_tripped: True` appears in the overview page, the bot has halted trading.
6. **Balance too low** — in paper mode, check `INITIAL_BALANCE_QUOTE`; in live mode the bot reads the real wallet balance at startup. If the balance is too low relative to the minimum order size, the position sizer will produce zero-size orders.

---

### "SQLITE_BUSY" or database errors

The dashboard and trading bot both access the database. Normally the WAL mode prevents conflicts. On slow machines or network filesystems, you may still see busy errors. Ensure the `./data` volume is on a local disk. If you continue to see them, consider switching to PostgreSQL (`DATABASE_URL=postgresql+psycopg2://...` in `.env`), which handles concurrent access more robustly.

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

See Section 11. The fastest fix is to disable the advisory crew in `settings.yaml`:

```yaml
advisory_enabled: false
```

This eliminates all LLM token usage while keeping the full deterministic trading loop running. Alternatively, raise `advisory_activation_threshold` to reduce how often the crew fires, or use the **Controls** page in the dashboard to pause the advisory crew temporarily without a restart.

---

### Dashboard shows "WebSocket disconnected"

The dashboard backend (`make dashboard-api`) needs to be running. Check that port 8000 is not blocked. If running with Docker, ensure both services started with `make docker-up`.

---

## 14. FAQ

**Q: Does the bot make money?**

**We don't know and won't claim it does.** The included strategies are educational implementations of common technical analysis methods. Past backtest performance does not guarantee future live results. Always paper-trade first and treat this as a research tool, not an income source.

---

**Q: Can I run multiple symbols at once?**

Yes. Edit `settings.yaml`:

```yaml
symbols:
  - "BTC/USDT"
  - "ETH/USDT"
  - "SOL/USDT"
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
- **Execution assumptions** — the legacy backtester fills at next-candle open with configurable slippage; real fills differ. The full simulation mode (see [Full simulation mode](#full-simulation-mode)) is more faithful since it runs the real `TradingFlow` with all guards
- **Small sample sizes** — a 90-day backtest with 20 trades is statistically weak

Use backtests to rule out obviously bad strategies, not to guarantee future profit.

---

*For developer documentation, see [DEVELOPER_MANUAL.md](DEVELOPER_MANUAL.md).*
*For the full configuration reference, see [docs/docs/configuration.md](docs/docs/configuration.md).*
*For architecture details, see [ARCHITECTURE.md](ARCHITECTURE.md).*
