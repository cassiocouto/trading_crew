# Configuration

Trading Crew is configured through environment variables (`.env` file) and
YAML files for CrewAI advisory agent/task definitions.

## Environment Variables

### Core

| Variable | Default | Description |
|----------|---------|-------------|
| `TRADING_MODE` | `paper` | `paper` or `live` |
| `EXCHANGE_ID` | `binance` | Any CCXT exchange ID |
| `EXCHANGE_API_KEY` | (empty) | Exchange API key |
| `EXCHANGE_API_SECRET` | (empty) | Exchange API secret |
| `EXCHANGE_SANDBOX` | `true` | Use exchange testnet |
| `SYMBOLS` | `["BTC/USDT"]` | Trading pairs (JSON list) |
| `DEFAULT_TIMEFRAME` | `1h` | OHLCV candle timeframe |
| `DATABASE_URL` | `sqlite:///trading_crew.db` | Database connection |
| `TELEGRAM_BOT_TOKEN` | (empty) | Telegram bot token |
| `TELEGRAM_CHAT_ID` | (empty) | Telegram chat ID |
| `OPENAI_API_KEY` | (empty) | LLM API key (advisory crew only) |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

### Scheduling

| Variable | Default | Description |
|----------|---------|-------------|
| `LOOP_INTERVAL_SECONDS` | `900` | Main loop cadence (15m default) |
| `EXECUTION_POLL_INTERVAL_SECONDS` | `900` | Open-order reconciliation interval |

### Market Intelligence Pipeline

| Variable | Default | Description |
|----------|---------|-------------|
| `MARKET_DATA_CANDLE_LIMIT` | `120` | Candle count fetched/analyzed per cycle |
| `MARKET_REGIME_VOLATILITY_THRESHOLD` | `0.03` | Regime volatile cutoff (`atr_14 / price`) |
| `MARKET_REGIME_TREND_THRESHOLD` | `0.01` | Regime trending cutoff (`|ema_fast-ema_slow| / price`) |
| `SENTIMENT_ENABLED` | `false` | Enable deterministic sentiment enrichment |
| `SENTIMENT_FEAR_GREED_ENABLED` | `true` | Enable Fear & Greed source |
| `SENTIMENT_FEAR_GREED_WEIGHT` | `1.0` | Source weight in confidence-weighted blend |
| `SENTIMENT_REQUEST_TIMEOUT_SECONDS` | `5` | HTTP timeout for sentiment source calls |

### Strategy Pipeline

| Variable | Default | Description |
|----------|---------|-------------|
| `ENSEMBLE_ENABLED` | `false` | Run strategies as ensemble (weighted voting) rather than individual |
| `ENSEMBLE_AGREEMENT_THRESHOLD` | `0.5` | Fraction of strategies that must agree for ensemble signal (0–1) |
| `STOP_LOSS_METHOD` | `fixed` | `fixed` (percentage) or `atr` (ATR-based, adapts to volatility) |
| `ATR_STOP_MULTIPLIER` | `2.0` | Number of ATRs used as stop distance when `STOP_LOSS_METHOD=atr` |

### Position Guards

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTI_AVERAGING_DOWN` | `true` | Reject new BUY signals if entry price ≤ existing position's stop-loss price |
| `SELL_GUARD_MODE` | `break_even` | `none` (disabled) or `break_even` (LIFO break-even guard on signal-driven sells) |
| `RISK__MIN_PROFIT_MARGIN_PCT` | `0.0` | Extra margin above break-even before a sell is approved (`0.0` = pure break-even) |
| `INITIAL_BALANCE_QUOTE` | `10000` | Starting balance for **paper trading only** — ignored in live mode |

### Live Wallet Sync (live mode only)

| Variable | Default | Description |
|----------|---------|-------------|
| `BALANCE_SYNC_INTERVAL_SECONDS` | `300` | How often (seconds) to re-sync wallet balance from the exchange. `0` = disabled. |
| `BALANCE_DRIFT_ALERT_THRESHOLD_PCT` | `1.0` | Send a Telegram alert when the synced balance drifts by this percentage or more. |

### Advisory Gate

| Variable | Default | Description |
|----------|---------|-------------|
| `ADVISORY_ENABLED` | `true` | Enable/disable advisory crew activation |
| `ADVISORY_ACTIVATION_THRESHOLD` | `0.6` | Uncertainty score at or above which advisory activates (0.0–1.0) |
| `ADVISORY_ESTIMATED_TOKENS` | `4000` | Estimated tokens per advisory crew run (for budget accounting) |

### Uncertainty Score Weights

| Variable | Default | Description |
|----------|---------|-------------|
| `UNCERTAINTY_WEIGHT_VOLATILE_REGIME` | `0.3` | Weight for volatile market regime factor |
| `UNCERTAINTY_WEIGHT_SENTIMENT_EXTREME` | `0.2` | Weight for extreme sentiment factor |
| `UNCERTAINTY_WEIGHT_LOW_SENTIMENT_CONFIDENCE` | `0.2` | Weight for low sentiment confidence factor |
| `UNCERTAINTY_WEIGHT_STRATEGY_DISAGREEMENT` | `0.3` | Weight for strategy disagreement factor |
| `UNCERTAINTY_WEIGHT_DRAWDOWN_PROXIMITY` | `0.2` | Weight for drawdown proximity factor |
| `UNCERTAINTY_WEIGHT_REGIME_CHANGE` | `0.3` | Weight for regime change factor |

### Daily Token Budget

| Variable | Default | Description |
|----------|---------|-------------|
| `DAILY_TOKEN_BUDGET_ENABLED` | `true` | Enable daily token budget guard |
| `DAILY_TOKEN_BUDGET_TOKENS` | `600000` | Estimated daily token cap |
| `TOKEN_BUDGET_DEGRADE_MODE` | `normal` | `normal` (advisory allowed) or `budget_stop` (advisory disabled when budget exhausted) |

## Deterministic Pipeline

The pipeline always runs deterministically — no LLM calls:

`fetch ticker/candles → store in DB → compute indicators/regime → run strategies → risk pipeline → execute`

This applies to all modes (paper and live). There are no pipeline mode switches.

### Regime Classification

Regime classification is tunable per deployment:

- `MARKET_REGIME_VOLATILITY_THRESHOLD` (default `0.03`)
- `MARKET_REGIME_TREND_THRESHOLD` (default `0.01`)

These values control how sensitive `"volatile"` and `"trending"` labels are.

If `SENTIMENT_ENABLED=true`, deterministic sentiment is added to
`MarketAnalysis.metadata` as:

- `sentiment_score` in `[-1, 1]`
- `sentiment_confidence` in `[0, 1]`
- `sentiment_sources` (source names used in aggregation)

### Strategy Modes

- **Individual** (`ENSEMBLE_ENABLED=false`): each strategy (EMA Crossover, Bollinger
  Bands, RSI Range) produces independent signals. All actionable signals above
  `min_confidence` pass to the risk pipeline.
- **Ensemble** (`ENSEMBLE_ENABLED=true`): strategies vote per symbol. A consensus
  signal is produced only when `ENSEMBLE_AGREEMENT_THRESHOLD` fraction of strategies
  agree on direction.

### Stop-loss Methods

- `fixed`: stop at `DEFAULT_STOP_LOSS_PCT` below/above entry price.
- `atr`: stop at `ATR_STOP_MULTIPLIER * ATR(14)` from entry, adapting to current
  volatility. Falls back to fixed when ATR is unavailable.

### Portfolio Tracking

**Paper mode:** the in-memory portfolio starts at `INITIAL_BALANCE_QUOTE` and is updated after each cycle's approved order requests.

**Live mode:** the portfolio balance is seeded directly from the exchange wallet at startup (via `fetch_balance()`). If the circuit breaker is open or the balance is zero, startup aborts with a clear error message. The balance is then re-synced every `BALANCE_SYNC_INTERVAL_SECONDS` seconds as a pre-cycle step (before any signal evaluation), so deposits and withdrawals made outside the bot are automatically reflected. A Telegram notification fires when the drift exceeds `BALANCE_DRIFT_ALERT_THRESHOLD_PCT`.

## Advisory Activation

When the deterministic pipeline completes, the `UncertaintyScorer` computes a
score from six weighted factors:

1. **Volatile regime** — proportion of symbols in `volatile` regime
2. **Sentiment extreme** — sentiment score ≥ 0.5 (absolute value)
3. **Low sentiment confidence** — sentiment confidence < 0.5
4. **Strategy disagreement** — strategies disagree on direction per symbol
5. **Drawdown proximity** — current drawdown as fraction of max allowed
6. **Regime change** — symbols whose regime changed since last cycle

If the score reaches `ADVISORY_ACTIVATION_THRESHOLD` (default 0.6), the
advisory crew activates. The crew reviews the pipeline's output and returns
directives such as:

- **veto_signal** — remove a signal for a specific symbol
- **adjust_confidence** — override a signal's confidence value
- **tighten_stop_loss** — set a tighter stop-loss percentage
- **reduce_position_size** — reduce position sizing
- **sit_out** — skip all signals for the cycle

After directives are applied to the signals, the risk pipeline re-runs to
re-derive order requests with correct position sizing.

### Tuning the Threshold

- **Lower threshold** (e.g. 0.3): advisory activates more often, higher LLM
  cost, more conservative trading
- **Higher threshold** (e.g. 0.8): advisory activates rarely, lower cost, more
  reliance on deterministic signals
- **`ADVISORY_ENABLED=false`**: advisory never activates; fully deterministic operation

### Tuning Uncertainty Weights

Each weight controls how much a specific factor contributes to the score. The
weights are not required to sum to 1.0 — the final score is capped at 1.0.
Increase a weight to make that factor more influential in triggering advisory.

## Daily Token Budget Degrade Mode

Token accounting applies **only to advisory crew activations** — the
deterministic pipeline uses zero LLM tokens.

- Budget starts at `DAILY_TOKEN_BUDGET_TOKENS`
- Each advisory run increments estimated usage by `ADVISORY_ESTIMATED_TOKENS`
- Counters automatically reset at UTC day rollover

### Degrade Levels

- `normal`: advisory allowed to activate when triggered; budget is tracked but
  does not disable advisory.
- `budget_stop`: when projected advisory cost would breach the daily budget,
  advisory is disabled for the rest of the UTC day. The deterministic pipeline
  continues operating normally.

## LLM Token Usage and Cost Estimation

LLM tokens are consumed **only when the advisory crew activates**. In calm
markets with clear strategy signals and low drawdown, many cycles run with zero
LLM cost.

### Estimation Formula

Use this per-advisory estimate:

`cost_per_advisory = (input_tokens / 1_000_000 * input_price_per_million) + (output_tokens / 1_000_000 * output_price_per_million)`

Then:

- `advisory_activations_per_day` = depends on market volatility and threshold
- `daily_cost = cost_per_advisory * advisory_activations_per_day`
- `monthly_cost ~= daily_cost * 30`

### Example Scenarios (illustrative)

Assumptions for examples below:

- Input price: `$0.15 / 1M` tokens
- Output price: `$0.60 / 1M` tokens
- Loop interval: `900s` (`96` cycles/day)

| Scenario | Advisory activations/day | Avg input tokens | Avg output tokens | Daily cost | Monthly cost (30d) |
|----------|--------------------------|------------------|-------------------|------------|--------------------|
| Calm market (threshold 0.6) | ~5 | 4,000 | 1,000 | $0.006 | $0.18 |
| Moderate volatility | ~20 | 4,000 | 1,000 | $0.024 | $0.72 |
| High volatility / low threshold | ~50 | 4,000 | 1,000 | $0.060 | $1.80 |
| Advisory disabled | 0 | 0 | 0 | $0.00 | $0.00 |

### Practical Measurement Workflow

1. Run the bot for 10-20 cycles with realistic settings.
2. Note how many cycles triggered advisory activation (logged at INFO level).
3. Capture total input/output tokens from your provider dashboard/logs.
4. Divide by advisory activation count to get average tokens/advisory.
5. Plug those values into the formula above.
6. Add 20-40% headroom for volatile periods.

### Cost Control Tips

- Increase `ADVISORY_ACTIVATION_THRESHOLD` to trigger advisory less often.
- Set `ADVISORY_ENABLED=false` for zero LLM cost (fully deterministic).
- Increase `LOOP_INTERVAL_SECONDS` to reduce total cycles (fewer potential activations).
- Use cheaper models for advisory tasks via `OPENAI_MODEL_NAME`.
- Use `TOKEN_BUDGET_DEGRADE_MODE=budget_stop` to cap daily spend.
- Tune uncertainty weights to reduce false activations.

## Risk Parameters

Risk parameters can be set via nested environment variables or in the
Settings class:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_position_size_pct` | 10% | Max single position size |
| `max_portfolio_exposure_pct` | 80% | Max total portfolio in positions |
| `max_drawdown_pct` | 15% | Circuit breaker threshold |
| `default_stop_loss_pct` | 3% | Default stop-loss distance |
| `risk_per_trade_pct` | 2% | Portfolio % risked per trade |
| `min_confidence` | 0.5 | Minimum signal confidence |

## CrewAI Agent Configuration

Advisory agent roles, goals, and backstories are defined in
`src/trading_crew/config/agents.yaml`. Task definitions are in
`src/trading_crew/config/tasks.yaml`. Edit these files to customize advisory
behavior without changing code.

## Example Configs

See the `examples/` directory for pre-built configurations:

- `config_paper_trade.yaml` — Safe simulation mode
- `config_binance.yaml` — Binance live trading
- `config_novadax.yaml` — NovaDAX BRL pairs (for silvia_v2 migrants)
