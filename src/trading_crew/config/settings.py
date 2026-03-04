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

    # -- Symbols to trade -----------------------------------------------------
    symbols: list[str] = Field(default=["BTC/USDT"])
    default_timeframe: str = "1h"

    # -- Database -------------------------------------------------------------
    database_url: str = "sqlite:///trading_crew.db"

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

    # -- Cost contention mode -------------------------------------------------
    cost_contention_enabled: bool = True
    market_crew_interval_seconds: int = Field(default=900, ge=10)
    strategy_crew_interval_seconds: int = Field(default=1800, ge=10)
    execution_crew_interval_seconds: int = Field(default=900, ge=10)

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
