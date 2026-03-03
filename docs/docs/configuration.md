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
| `LOG_LEVEL` | `INFO` | Logging verbosity |

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
