"""Application settings powered by Pydantic Settings.

Configuration is loaded in this priority order (highest wins):
  1. Environment variables (or .env file)
  2. Defaults defined here

All secrets (API keys, tokens) come from the environment — never from
checked-in files.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from trading_crew.models.risk import RiskParams

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class TradingMode(StrEnum):
    """Operating mode for the trading system."""

    PAPER = "paper"
    LIVE = "live"


class TokenBudgetDegradeMode(StrEnum):
    """Maximum degrade stage allowed after daily budget pressure."""

    OFF = "off"
    STRATEGY_ONLY = "strategy_only"
    HARD_STOP = "hard_stop"


class MarketPipelineMode(StrEnum):
    """How market intelligence should execute each due cycle."""

    CREWAI = "crewai"
    DETERMINISTIC = "deterministic"
    HYBRID = "hybrid"


class StrategyPipelineMode(StrEnum):
    """How the strategy/risk pipeline should execute each due cycle."""

    CREWAI = "crewai"
    DETERMINISTIC = "deterministic"
    HYBRID = "hybrid"


class ExecutionPipelineMode(StrEnum):
    """How the execution pipeline should place and monitor orders each cycle."""

    CREWAI = "crewai"
    DETERMINISTIC = "deterministic"
    HYBRID = "hybrid"


class StopLossMethod(StrEnum):
    """How stop-loss prices are calculated."""

    FIXED = "fixed"
    ATR = "atr"


class TelegramNotifyLevel(StrEnum):
    """Which events trigger a Telegram alert."""

    ALL = "all"
    TRADES_ONLY = "trades_only"
    CRITICAL_ONLY = "critical_only"


class Settings(BaseSettings):
    """Central application configuration.

    Values are read from environment variables. A ``.env`` file in the project
    root is loaded automatically.
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -- Trading mode ---------------------------------------------------------
    trading_mode: TradingMode = TradingMode.PAPER

    # -- Exchange -------------------------------------------------------------
    exchange_id: str = "binance"
    exchange_api_key: str = ""
    exchange_api_secret: str = ""
    exchange_password: str = ""
    exchange_sandbox: bool = True
    # API-level rate-limit circuit breaker
    exchange_rate_limit_threshold: int = Field(default=5, ge=1)
    exchange_rate_limit_cooldown_seconds: int = Field(default=60, ge=1)

    # -- Symbols to trade -----------------------------------------------------
    symbols: list[str] = Field(default=["BTC/USDT"])
    default_timeframe: str = "1h"

    # -- Database -------------------------------------------------------------
    database_url: str = "sqlite:///trading_crew.db"
    # Connection pool settings (used for non-SQLite databases like PostgreSQL)
    database_pool_size: int = Field(default=5, ge=1)
    database_max_overflow: int = Field(default=10, ge=0)
    database_pool_timeout: int = Field(default=30, ge=1)

    # -- Telegram (optional) --------------------------------------------------
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # -- LLM for CrewAI -------------------------------------------------------
    openai_api_key: str = ""
    openai_api_base: str = ""
    openai_model_name: str = "gpt-4o-mini"

    # -- Risk management ------------------------------------------------------
    risk: RiskParams = Field(default_factory=RiskParams)

    # -- Trading loop ---------------------------------------------------------
    loop_interval_seconds: int = Field(default=900, ge=10)
    stale_order_cancel_minutes: int = Field(default=10, ge=1)
    stale_partial_fill_cancel_minutes: int = Field(default=360, ge=1)

    # -- Cost contention mode -------------------------------------------------
    cost_contention_enabled: bool = True
    market_crew_interval_seconds: int = Field(default=900, ge=10)
    strategy_crew_interval_seconds: int = Field(default=1800, ge=10)
    execution_crew_interval_seconds: int = Field(default=900, ge=10)

    # -- Execution pipeline (Phase 4) -----------------------------------------
    execution_pipeline_mode: ExecutionPipelineMode = ExecutionPipelineMode.DETERMINISTIC

    # -- Strategy pipeline (Phase 3) ------------------------------------------
    strategy_pipeline_mode: StrategyPipelineMode = StrategyPipelineMode.DETERMINISTIC
    ensemble_enabled: bool = False
    ensemble_agreement_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    stop_loss_method: StopLossMethod = StopLossMethod.FIXED
    atr_stop_multiplier: float = Field(default=2.0, gt=0.0, le=10.0)
    initial_balance_quote: float = Field(
        default=10_000.0,
        gt=0.0,
        description=(
            "Starting balance for paper trading only. "
            "Ignored in live mode — the exchange wallet balance is used instead."
        ),
    )

    # -- Live wallet sync (ignored in paper mode) -----------------------------
    balance_sync_interval_seconds: int = Field(
        default=300,
        ge=0,
        description=(
            "How often (seconds) to re-sync portfolio.balance_quote from the exchange "
            "in live mode. Set to 0 to disable. Has no effect in paper mode."
        ),
    )
    balance_drift_alert_threshold_pct: float = Field(
        default=1.0,
        ge=0.0,
        description=(
            "Send a Telegram notification when the synced balance drifts by this "
            "percentage or more from the in-memory value."
        ),
    )

    # -- Market intelligence pipeline -----------------------------------------
    market_pipeline_mode: MarketPipelineMode = MarketPipelineMode.DETERMINISTIC
    market_data_candle_limit: int = Field(default=120, ge=20, le=1000)
    market_regime_volatility_threshold: float = Field(default=0.03, ge=0.0, le=1.0)
    market_regime_trend_threshold: float = Field(default=0.01, ge=0.0, le=1.0)
    sentiment_enabled: bool = False
    sentiment_fear_greed_enabled: bool = True
    sentiment_fear_greed_weight: float = Field(default=1.0, ge=0.0)
    sentiment_request_timeout_seconds: int = Field(default=5, ge=1, le=30)

    # -- Daily token budget guard ---------------------------------------------
    daily_token_budget_enabled: bool = True
    daily_token_budget_tokens: int = Field(default=600_000, ge=1)
    token_budget_degrade_mode: TokenBudgetDegradeMode = TokenBudgetDegradeMode.STRATEGY_ONLY
    non_llm_monitor_on_hard_stop: bool = True
    market_crew_estimated_tokens: int = Field(default=1_500, ge=0)
    strategy_crew_estimated_tokens: int = Field(default=6_000, ge=0)
    execution_crew_estimated_tokens: int = Field(default=1_000, ge=0)

    # -- Flow orchestration (Phase 5) -----------------------------------------
    save_cycle_history: bool = True
    stop_loss_monitoring_enabled: bool = True

    # -- Dashboard (Phase 7) --------------------------------------------------
    dashboard_enabled: bool = True
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8000
    dashboard_cors_origins: list[str] = Field(default=["http://localhost:3000"])
    dashboard_api_key: str = ""
    dashboard_ws_poll_interval_seconds: int = Field(default=3, ge=1, le=60)

    # -- Telegram alert level (Phase 7) ---------------------------------------
    telegram_notify_level: TelegramNotifyLevel = TelegramNotifyLevel.TRADES_ONLY

    # -- Logging --------------------------------------------------------------
    log_level: str = "INFO"

    # -- Paths ----------------------------------------------------------------
    config_dir: Path = Field(default=PROJECT_ROOT / "src" / "trading_crew" / "config")

    @property
    def agents_yaml_path(self) -> Path:
        """Path to the CrewAI agents definition file."""
        return self.config_dir / "agents.yaml"

    @property
    def tasks_yaml_path(self) -> Path:
        """Path to the CrewAI tasks definition file."""
        return self.config_dir / "tasks.yaml"

    @property
    def quote_currency(self) -> str:
        """Quote currency derived from the first configured symbol (e.g. BTC/USDT → USDT)."""
        return self.symbols[0].split("/")[1] if self.symbols else "USDT"

    @property
    def is_paper(self) -> bool:
        """Whether the system is running in paper-trading mode."""
        return self.trading_mode == TradingMode.PAPER

    @property
    def is_live(self) -> bool:
        """Whether the system is running in live-trading mode."""
        return self.trading_mode == TradingMode.LIVE

    @property
    def telegram_enabled(self) -> bool:
        """Whether Telegram notifications are configured."""
        return bool(self.telegram_bot_token and self.telegram_chat_id)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached singleton Settings instance."""
    return Settings()
