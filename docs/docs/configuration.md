# Configuration

Trading Crew is configured through environment variables (`.env` file) and
YAML files for CrewAI agent/task definitions.

## Environment Variables

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
| `OPENAI_API_KEY` | (empty) | LLM API key for CrewAI |
| `LOOP_INTERVAL_SECONDS` | `900` | Main loop cadence (15m default) |
| `COST_CONTENTION_ENABLED` | `true` | Enable interval-gated crew execution |
| `MARKET_CREW_INTERVAL_SECONDS` | `900` | Market crew schedule |
| `STRATEGY_CREW_INTERVAL_SECONDS` | `1800` | Strategy crew schedule |
| `EXECUTION_CREW_INTERVAL_SECONDS` | `900` | Execution crew schedule |
| `MARKET_PIPELINE_MODE` | `deterministic` | `deterministic`, `crewai`, or `hybrid` |
| `MARKET_DATA_CANDLE_LIMIT` | `120` | Candle count fetched/analyzed per market cycle |
| `MARKET_REGIME_VOLATILITY_THRESHOLD` | `0.03` | Regime volatile cutoff (`atr_14 / price`) |
| `MARKET_REGIME_TREND_THRESHOLD` | `0.01` | Regime trending cutoff (`\|ema_fast-ema_slow\| / price`) |
| `SENTIMENT_ENABLED` | `false` | Enable optional deterministic sentiment enrichment |
| `SENTIMENT_FEAR_GREED_ENABLED` | `true` | Enable Fear & Greed source |
| `SENTIMENT_FEAR_GREED_WEIGHT` | `1.0` | Source weight in confidence-weighted blend |
| `SENTIMENT_REQUEST_TIMEOUT_SECONDS` | `5` | HTTP timeout for sentiment source calls |
| `DAILY_TOKEN_BUDGET_ENABLED` | `true` | Enable daily budget guard (estimated tokens) |
| `DAILY_TOKEN_BUDGET_TOKENS` | `600000` | Estimated daily token cap |
| `TOKEN_BUDGET_DEGRADE_MODE` | `strategy_only` | `off`, `strategy_only`, or `hard_stop` |
| `NON_LLM_MONITOR_ON_HARD_STOP` | `true` | Keep lightweight open-order probe running in hard-stop |
| `MARKET_CREW_ESTIMATED_TOKENS` | `1500` | Estimated token cost per market crew run |
| `STRATEGY_CREW_ESTIMATED_TOKENS` | `6000` | Estimated token cost per strategy crew run |
| `EXECUTION_CREW_ESTIMATED_TOKENS` | `1000` | Estimated token cost per execution crew run |
| `STRATEGY_PIPELINE_MODE` | `deterministic` | `deterministic`, `crewai`, or `hybrid` — strategy/risk execution mode |
| `ENSEMBLE_ENABLED` | `false` | Run strategies as ensemble (weighted voting) rather than individual |
| `ENSEMBLE_AGREEMENT_THRESHOLD` | `0.5` | Fraction of strategies that must agree for ensemble signal (0–1) |
| `STOP_LOSS_METHOD` | `fixed` | `fixed` (percentage) or `atr` (ATR-based, adapts to volatility) |
| `ATR_STOP_MULTIPLIER` | `2.0` | Number of ATRs used as stop distance when `STOP_LOSS_METHOD=atr` |
| `ANTI_AVERAGING_DOWN` | `true` | Reject new BUY signals if entry price ≤ existing position's stop-loss price |
| `SELL_GUARD_MODE` | `break_even` | `none` (disabled) or `break_even` (LIFO break-even guard on signal-driven sells) |
| `RISK__MIN_PROFIT_MARGIN_PCT` | `0.0` | Extra margin above break-even before a sell is approved (`0.0` = pure break-even) |
| `INITIAL_BALANCE_QUOTE` | `10000` | Starting balance for **paper trading only** — ignored in live mode (exchange wallet is used instead) |
| `BALANCE_SYNC_INTERVAL_SECONDS` | `300` | How often (seconds) to re-sync wallet balance from the exchange in live mode. `0` = disabled. No effect in paper mode. |
| `BALANCE_DRIFT_ALERT_THRESHOLD_PCT` | `1.0` | Send a Telegram alert when the synced balance drifts by this percentage or more from the in-memory value. |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

## Early Cost Contention Phase (default)

Trading Crew now defaults to a cost-aware cadence:

- Base loop: every 15 minutes (`LOOP_INTERVAL_SECONDS=900`)
- Market crew: every 15 minutes
- Strategy crew: every 30 minutes
- Execution crew: every 15 minutes, and skipped when not due and no open orders exist

This avoids 60-second LLM-driven scalping behavior, which is often uneconomical
after token costs.

### Phase 2 Market Pipeline

Phase 2 introduces a deterministic market pipeline:

`fetch ticker/candles -> store in DB -> compute indicators/regime`

By default, `MARKET_PIPELINE_MODE=deterministic`, so Market Intelligence can run
without depending on LLM output parsing. This lowers token spend and makes market
data + analysis reproducible. Set `hybrid` if you want both deterministic and
CrewAI market execution in parallel.

Regime classification is tunable per deployment:

- `MARKET_REGIME_VOLATILITY_THRESHOLD` (default `0.03`)
- `MARKET_REGIME_TREND_THRESHOLD` (default `0.01`)

These values control how sensitive `"volatile"` and `"trending"` labels are.

If `SENTIMENT_ENABLED=true`, deterministic sentiment is added to
`MarketAnalysis.metadata` as:

- `sentiment_score` in `[-1, 1]`
- `sentiment_confidence` in `[0, 1]`
- `sentiment_sources` (source names used in aggregation)

### Phase 3 Strategy Pipeline

Phase 3 introduces a deterministic strategy + risk pipeline:

`MarketAnalysis -> StrategyRunner -> RiskPipeline -> OrderRequest`

By default, `STRATEGY_PIPELINE_MODE=deterministic`, so signals are generated and
risk-validated without LLM involvement. Set `hybrid` to run both deterministic and
CrewAI strategy evaluation.

#### Strategy modes

- **Individual** (`ENSEMBLE_ENABLED=false`): each strategy (EMA Crossover, Bollinger
  Bands, RSI Range) produces independent signals. All actionable signals above
  `min_confidence` pass to the risk pipeline.
- **Ensemble** (`ENSEMBLE_ENABLED=true`): strategies vote per symbol. A consensus
  signal is produced only when `ENSEMBLE_AGREEMENT_THRESHOLD` fraction of strategies
  agree on direction.

#### Stop-loss methods

- `fixed`: stop at `DEFAULT_STOP_LOSS_PCT` below/above entry price.
- `atr`: stop at `ATR_STOP_MULTIPLIER * ATR(14)` from entry, adapting to current
  volatility. Falls back to fixed when ATR is unavailable.

#### Portfolio tracking

**Paper mode:** the in-memory portfolio starts at `INITIAL_BALANCE_QUOTE` and is updated after each cycle's approved order requests.

**Live mode:** the portfolio balance is seeded directly from the exchange wallet at startup (via `fetch_balance()`). If the circuit breaker is open or the balance is zero, startup aborts with a clear error message. The balance is then re-synced every `BALANCE_SYNC_INTERVAL_SECONDS` seconds as a pre-cycle step (before any signal evaluation), so deposits and withdrawals made outside the bot are automatically reflected. A Telegram notification fires when the drift exceeds `BALANCE_DRIFT_ALERT_THRESHOLD_PCT`.

### Daily Budget Degrade Mode

A second guard now runs by default: estimated daily token accounting in UTC.

- Budget starts at `DAILY_TOKEN_BUDGET_TOKENS`
- Each crew run increments estimated usage by its configured estimate
- Behavior is controlled by `TOKEN_BUDGET_DEGRADE_MODE`
- Counters automatically reset at UTC day rollover

This protects net profitability by reducing expensive decision cycles when costs
run too high.

#### Degrade levels

- `off`: no budget-triggered degrade.
- `strategy_only`: when projected Strategy cost would breach budget, Strategy crew
  is disabled for the rest of the UTC day.
- `hard_stop`: includes `strategy_only`; once budget is fully exhausted, all LLM
  crews are skipped until UTC reset.

In `hard_stop` mode, optional non-LLM order probing continues each cycle when
`NON_LLM_MONITOR_ON_HARD_STOP=true`.

## LLM Token Usage and Cost Estimation

CrewAI does not consume tokens continuously on its own. Tokens are consumed when
you execute agent tasks (for this project, each crew `kickoff()` call).

In the default loop, three crews run each cycle:

- Market crew
- Strategy crew
- Execution crew

### Estimation Formula

Use this per-cycle estimate:

`cost_per_cycle = (input_tokens_per_cycle / 1_000_000 * input_price_per_million) + (output_tokens_per_cycle / 1_000_000 * output_price_per_million)`

Then:

- `cycles_per_day = 86400 / loop_interval_seconds`
- `daily_cost = cost_per_cycle * cycles_per_day`
- `monthly_cost ~= daily_cost * 30`

At `loop_interval_seconds = 900`, you run `96` cycles/day.

### Example Scenarios (illustrative)

Assumptions for examples below:

- Input price: `$0.15 / 1M` tokens
- Output price: `$0.60 / 1M` tokens
- Loop interval: `900s` (`96` cycles/day)

| Scenario | Avg input tokens/cycle | Avg output tokens/cycle | Cost/cycle | Daily cost | Monthly cost (30d) |
|----------|--------------------------|--------------------------|------------|------------|--------------------|
| Lean prompts | 2,000 | 500 | $0.0006 | $0.06 | $1.80 |
| Typical dev run | 8,000 | 2,000 | $0.0024 | $0.23 | $6.90 |
| Verbose/heavy context | 20,000 | 5,000 | $0.0060 | $0.58 | $17.28 |

### Practical Measurement Workflow

1. Run the bot for 10-20 cycles with realistic settings.
2. Capture total input/output tokens from your provider dashboard/logs.
3. Divide by cycle count to get average tokens/cycle.
4. Plug those values into the formula above.
5. Add 20-40% headroom for volatility.

### Cost Control Tips

- Increase `loop_interval_seconds` (largest direct reduction in spend).
- Skip strategy/execution crews when no fresh market change exists.
- Keep tool outputs short (avoid large JSON payloads per task).
- Use cheaper models for routine cycles and stronger models only when needed.
- Limit max tokens per task to cap worst-case responses.

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

Agent roles, goals, and backstories are defined in
`src/trading_crew/config/agents.yaml`. Edit this file to customize agent
behavior without changing code.

## Example Configs

See the `examples/` directory for pre-built configurations:

- `config_paper_trade.yaml` — Safe simulation mode
- `config_binance.yaml` — Binance live trading
- `config_novadax.yaml` — NovaDAX BRL pairs (for silvia_v2 migrants)
