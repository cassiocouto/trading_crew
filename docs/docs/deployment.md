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

## Docker (Coming Soon)

A Dockerfile will be provided in Phase 8 for containerized deployment.

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

## Monitoring

- **Telegram**: Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` for trade
  alerts and error notifications
- **Log files**: Monitor `trading_crew.log` for detailed operation logs
- **Database**: Query the `pnl_snapshots` table for equity curve data
