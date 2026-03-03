# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
