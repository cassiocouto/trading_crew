# Contributing to Trading Crew

Thank you for your interest in contributing! This guide will help you get
started.

## Code of Conduct

By participating in this project, you agree to abide by our
[Code of Conduct](CODE_OF_CONDUCT.md).

## Getting Started

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Git

### Local Development Setup

```bash
# 1. Fork and clone the repository
git clone https://github.com/YOUR_USERNAME/trading-crew.git
cd trading-crew

# 2. Install all dependencies (dev, docs, notifications)
make dev

# 3. Copy environment template
cp .env.example .env
# Edit .env with your values (paper trading mode is the default)

# 4. Run tests to verify setup
make test

# 5. Run linter
make lint
```

## How to Contribute

### Reporting Bugs

Use the [Bug Report](https://github.com/your-org/trading-crew/issues/new?template=bug_report.yml)
issue template. Include:

- Steps to reproduce the issue
- Expected vs actual behavior
- Python version, OS, and relevant config (redact secrets!)
- Logs (redact any API keys or personal information)

### Suggesting Features

Use the [Feature Request](https://github.com/your-org/trading-crew/issues/new?template=feature_request.yml)
issue template.

### Contributing a New Strategy

Trading strategies are the most common community contribution. To add one:

1. Create a new file in `src/trading_crew/strategies/`
2. Inherit from `BaseStrategy` and implement `generate_signal()`
3. Add unit tests in `tests/unit/strategies/`
4. Validate with paper trading
5. Submit a PR using the "New Strategy" label

See [Writing a Strategy](docs/docs/writing-a-strategy.md) for a detailed guide.

### Pull Request Process

1. **Create a feature branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following the code standards below

3. **Run the full quality suite**:
   ```bash
   make format      # Auto-format
   make lint         # Linter
   make type-check   # Type checker
   make test         # All tests
   ```

4. **Commit** with a clear message:
   ```bash
   git commit -m "feat: add RSI divergence strategy"
   ```
   We follow [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat:` new features
   - `fix:` bug fixes
   - `docs:` documentation changes
   - `test:` adding or updating tests
   - `refactor:` code restructuring without behavior change
   - `chore:` maintenance tasks

5. **Push and open a PR** against `main`

6. **Fill out the PR template** — ensure:
   - All CI checks pass
   - No secrets are committed
   - Paper-trading validation was performed (for strategy/execution changes)
   - Tests cover new functionality

## Code Standards

- **Type hints**: All public functions must have type annotations
- **Docstrings**: All public modules, classes, and functions need docstrings
  (Google style)
- **Formatting**: Enforced by `ruff format` (line length 100)
- **Linting**: Must pass `ruff check` with no errors
- **Testing**: New features require tests; aim for >80% coverage on new code

## Security

- **NEVER** commit API keys, secrets, or credentials
- **NEVER** commit `.env` files
- The `detect-secrets` pre-commit hook will block commits containing secrets
- If you discover a security vulnerability, please report it privately
  (do not open a public issue)

## Questions?

Open a [Discussion](https://github.com/your-org/trading-crew/discussions) for
questions that aren't bugs or feature requests.
