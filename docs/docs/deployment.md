# Deployment

Guide for running Trading Crew in production.

!!! warning
    Read the [Disclaimer](../../DISCLAIMER.md) before running in live mode.
    You are solely responsible for any financial losses.

## Paper Trading (Recommended Start)

Always start with paper trading to validate your configuration:

```bash
make paper-trade
```

The system runs a fully deterministic pipeline — no LLM calls are required to
operate. If `ADVISORY_ENABLED=true` and an `OPENAI_API_KEY` is set, the
advisory crew will activate when the uncertainty score exceeds the threshold.

## Live Trading

When you're confident in your configuration:

```bash
# This shows a warning and waits 5 seconds before starting
make live-trade
```

Or set the environment variable directly:

```bash
TRADING_MODE=live uv run trading-crew
```

In live mode the same deterministic pipeline runs. The only difference is that
orders are placed on the real exchange via CCXT instead of being simulated
locally.

## Fully Deterministic Operation

To run with zero LLM involvement (no advisory crew at all), set:

```bash
ADVISORY_ENABLED=false
```

This is safe for unattended production deployment. The deterministic pipeline
handles all market data, signal generation, risk management, and order
execution without any external LLM dependency.

## Docker (Coming Soon)

A Dockerfile will be provided for containerized deployment.

## Database

### SQLite (Development)

The default `sqlite:///trading_crew.db` works for local development.

### PostgreSQL (Production)

For production, use PostgreSQL with the sync psycopg2 driver:

```bash
DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/trading_crew
```

Run migrations:

```bash
make db-upgrade
```

## Logging

Logs are written to both stdout and `trading_crew.log`. Configure the
level with `LOG_LEVEL` (DEBUG, INFO, WARNING, ERROR).

Key log messages to watch for:

- `Uncertainty score: X.XXX (threshold: X.XX, recommend_advisory: True/False)` —
  logged every cycle, shows whether advisory will activate
- `Advisory applied N adjustments` — logged when advisory modifies signals
- `Strategy pipeline: N signals, N risk-approved, N order requests` —
  per-cycle summary of the deterministic pipeline

## Monitoring

- **Telegram**: Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` for trade
  alerts, circuit breaker notifications, and error reports
- **Log files**: Monitor `trading_crew.log` for detailed operation logs
- **Database**: Query the `pnl_snapshots` table for equity curve data;
  query `cycle_summaries` for per-cycle advisory activation and uncertainty
  scores
- **Dashboard**: The FastAPI + Next.js dashboard provides real-time visibility
  into portfolio state, orders, signals, and advisory crew activity

## Health Checks

The deterministic pipeline requires only exchange API connectivity. Check:

1. **Exchange API**: CCXT can reach the exchange (test with `fetch_ticker`)
2. **Database**: SQLite file or PostgreSQL connection is writable
3. **LLM (optional)**: Only needed if `ADVISORY_ENABLED=true`; the system
   gracefully continues without advisory if the LLM call fails
