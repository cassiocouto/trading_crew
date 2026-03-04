# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### Phase 3: Strategy Crew
- **StrategyRunner** service — deterministic strategy execution engine with
  individual and ensemble (weighted voting) modes
- **RiskPipeline** service — full risk validation pipeline: confidence filter,
  circuit breaker, position sizing, stop-loss (fixed % or ATR-based), portfolio
  exposure limits, and concentration limits
- **CompositeStrategy** — ensemble strategy that aggregates signals from
  multiple child strategies via configurable agreement threshold
- **RunStrategiesTool** — CrewAI tool wrapping StrategyRunner for the
  Strategist agent
- **EvaluateRiskTool** — CrewAI tool wrapping RiskPipeline for the Risk
  Manager agent
- `StrategyPipelineMode` setting (crewai/deterministic/hybrid)
- Configurable stop-loss method (`STOP_LOSS_METHOD`: fixed/atr)
- Ensemble mode settings (`ENSEMBLE_ENABLED`, `ENSEMBLE_AGREEMENT_THRESHOLD`)
- Initial portfolio balance setting (`INITIAL_BALANCE_QUOTE`)
- `CycleState.order_requests` field for risk-approved order requests
- 36 new unit tests for StrategyRunner, RiskPipeline, and CompositeStrategy
- Strategist and Risk Manager agents now receive deterministic tools

#### Phase 2: Market Intelligence
- Deterministic market intelligence pipeline (fetch → analyze → store)
- TechnicalAnalyzer with EMA, RSI, Bollinger Bands, MACD, ATR, and regime
  classification
- MarketIntelligenceService for coordinated multi-symbol analysis
- Optional sentiment enrichment (Fear & Greed Index)
- Configurable market regime thresholds
- Cost contention scheduling with daily token budget guards
- `MarketPipelineMode` setting (crewai/deterministic/hybrid)
- `MarketMetadata` typed model for structured analysis metadata
- `CycleState` DTO for inter-crew data handoff

#### Phase 1: Foundation
- Project scaffolding with pyproject.toml, Makefile, and uv support
- Apache 2.0 license and financial disclaimer
- Open-source community files (CONTRIBUTING, CODE_OF_CONDUCT, ARCHITECTURE)
- GitHub Actions CI pipeline, issue templates, and PR template
- Pydantic data models for market, signals, orders, portfolio, and risk
- Configuration system using Pydantic Settings with .env and YAML support
- SQLAlchemy ORM models and Alembic migration setup
- CCXT-based multi-exchange service facade
- CrewAI agent, crew, and tool scaffolding
- Paper trading as the default mode
- Example configurations for Binance and NovaDAX
