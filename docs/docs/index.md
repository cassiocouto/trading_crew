# Trading Crew

**Deterministic-first crypto trading system with conditional AI advisory.**

Trading Crew runs a fully deterministic pipeline for cryptocurrency trading —
fetching market data, computing indicators, generating signals, and managing
risk — all without LLM calls. An optional advisory crew activates only when
the uncertainty score exceeds a configurable threshold, providing AI-powered
review of the pipeline output.

## Key Features

- **Deterministic-First** — The entire pipeline runs without LLM calls by default
- **Uncertainty-Gated Advisory** — AI advisory activates only when market
  conditions are uncertain (configurable threshold)
- **Multi-Exchange** — 100+ exchanges via CCXT
- **Risk-First** — Position sizing, stop-loss, portfolio limits, circuit breakers
- **Paper Trading Default** — Safe to experiment with
- **Token-Efficient** — LLM tokens consumed only during advisory activations,
  not every cycle
- **Pluggable Strategies** — Easy to add your own

## Quick Links

- [Getting Started](getting-started.md) — Install and run in 5 minutes
- [Configuration](configuration.md) — All settings explained
- [Architecture](../../ARCHITECTURE.md) — System design, advisory activation, and budget policy
- [Writing a Strategy](writing-a-strategy.md) — Contribute your own strategy
- [Deployment](deployment.md) — Run in production
