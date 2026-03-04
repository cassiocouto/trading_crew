"""Infrastructure services.

This package contains services that bridge the domain logic with external
systems: exchanges, databases, and notification channels.

Modules:
    exchange_service             — CCXT multi-exchange facade
    market_intelligence_service  — Deterministic fetch/analyze/store pipeline
    technical_analyzer           — Shared indicator/regime computation engine
    sentiment_service            — Optional external sentiment aggregation
    strategy_runner              — Deterministic strategy execution engine
    risk_pipeline                — Signal -> risk validation -> order request
    database_service             — Persistence operations for orders, positions, etc.
    notification_service         — Telegram and webhook notifications
"""
