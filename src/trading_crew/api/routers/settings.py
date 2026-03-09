"""Settings REST endpoints — read and write non-secret settings.yaml."""

from __future__ import annotations

import logging

import yaml
from fastapi import APIRouter, HTTPException

from trading_crew.api.schemas import RiskParamsResponse, SettingsResponse, SettingsUpdate
from trading_crew.config.settings import _SETTINGS_YAML, clear_settings_cache, get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["settings"])


def _build_response(
    include_advisory_llm: bool = True,
) -> SettingsResponse:
    """Build a SettingsResponse from the current (possibly fresh) settings."""
    s = get_settings()
    return SettingsResponse(
        trading_mode=s.trading_mode.value,
        exchange_id=s.exchange_id,
        exchange_sandbox=s.exchange_sandbox,
        exchange_rate_limit_threshold=s.exchange_rate_limit_threshold,
        exchange_rate_limit_cooldown_seconds=s.exchange_rate_limit_cooldown_seconds,
        symbols=s.symbols,
        default_timeframe=s.default_timeframe,
        loop_interval_seconds=s.loop_interval_seconds,
        execution_poll_interval_seconds=s.execution_poll_interval_seconds,
        stale_order_cancel_minutes=s.stale_order_cancel_minutes,
        stale_partial_fill_cancel_minutes=s.stale_partial_fill_cancel_minutes,
        ensemble_enabled=s.ensemble_enabled,
        ensemble_agreement_threshold=s.ensemble_agreement_threshold,
        stop_loss_method=s.stop_loss_method.value,
        atr_stop_multiplier=s.atr_stop_multiplier,
        initial_balance_quote=s.initial_balance_quote,
        anti_averaging_down=s.anti_averaging_down,
        sell_guard_mode=s.sell_guard_mode.value,
        balance_sync_interval_seconds=s.balance_sync_interval_seconds,
        balance_drift_alert_threshold_pct=s.balance_drift_alert_threshold_pct,
        market_data_candle_limit=s.market_data_candle_limit,
        market_regime_volatility_threshold=s.market_regime_volatility_threshold,
        market_regime_trend_threshold=s.market_regime_trend_threshold,
        sentiment_enabled=s.sentiment_enabled,
        sentiment_fear_greed_enabled=s.sentiment_fear_greed_enabled,
        sentiment_fear_greed_weight=s.sentiment_fear_greed_weight,
        sentiment_request_timeout_seconds=s.sentiment_request_timeout_seconds,
        advisory_enabled=s.advisory_enabled,
        advisory_activation_threshold=s.advisory_activation_threshold,
        advisory_estimated_tokens=s.advisory_estimated_tokens,
        uncertainty_weight_volatile_regime=s.uncertainty_weight_volatile_regime,
        uncertainty_weight_sentiment_extreme=s.uncertainty_weight_sentiment_extreme,
        uncertainty_weight_low_sentiment_confidence=s.uncertainty_weight_low_sentiment_confidence,
        uncertainty_weight_strategy_disagreement=s.uncertainty_weight_strategy_disagreement,
        uncertainty_weight_drawdown_proximity=s.uncertainty_weight_drawdown_proximity,
        uncertainty_weight_regime_change=s.uncertainty_weight_regime_change,
        daily_token_budget_enabled=s.daily_token_budget_enabled,
        daily_token_budget_tokens=s.daily_token_budget_tokens,
        token_budget_degrade_mode=s.token_budget_degrade_mode.value,
        save_cycle_history=s.save_cycle_history,
        stop_loss_monitoring_enabled=s.stop_loss_monitoring_enabled,
        dashboard_enabled=s.dashboard_enabled,
        dashboard_host=s.dashboard_host,
        dashboard_port=s.dashboard_port,
        dashboard_cors_origins=s.dashboard_cors_origins,
        dashboard_ws_poll_interval_seconds=s.dashboard_ws_poll_interval_seconds,
        telegram_notify_level=s.telegram_notify_level.value,
        crewai_verbose=s.crewai_verbose,
        log_level=s.log_level,
        risk=RiskParamsResponse(
            max_position_size_pct=s.risk.max_position_size_pct,
            max_portfolio_exposure_pct=s.risk.max_portfolio_exposure_pct,
            max_drawdown_pct=s.risk.max_drawdown_pct,
            default_stop_loss_pct=s.risk.default_stop_loss_pct,
            risk_per_trade_pct=s.risk.risk_per_trade_pct,
            min_confidence=s.risk.min_confidence,
            cooldown_after_loss_seconds=s.risk.cooldown_after_loss_seconds,
            min_profit_margin_pct=s.risk.min_profit_margin_pct,
        ),
        advisory_llm_configured=s.advisory_llm_configured if include_advisory_llm else False,
    )


@router.get("/", response_model=SettingsResponse)
def get_settings_endpoint() -> SettingsResponse:
    """Return current non-secret settings."""
    return _build_response()


@router.put("/", response_model=SettingsResponse)
def update_settings(body: SettingsUpdate) -> SettingsResponse:
    """Merge the provided values into settings.yaml and return updated settings.

    Only non-None fields are written.  Secret fields cannot be set here — use
    the .env file for API keys and tokens.
    """
    # Load existing YAML (or start fresh)
    if _SETTINGS_YAML.exists():
        try:
            existing: dict = yaml.safe_load(_SETTINGS_YAML.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"Failed to read settings.yaml: {exc}"
            ) from exc
    else:
        existing = {}

    # Merge non-None fields from the update payload
    update_data = body.model_dump(exclude_none=True)

    # Handle risk nested dict specially — merge instead of replace
    if "risk" in update_data and isinstance(update_data["risk"], dict):
        existing_risk = existing.get("risk", {}) or {}
        existing_risk.update(update_data.pop("risk"))
        existing["risk"] = existing_risk

    existing.update(update_data)

    # Write back atomically
    try:
        tmp = _SETTINGS_YAML.with_suffix(".tmp.yaml")
        tmp.write_text(
            yaml.dump(existing, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        import os

        os.replace(tmp, _SETTINGS_YAML)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to write settings.yaml: {exc}"
        ) from exc

    # Bust the cache so the API reflects the new values immediately
    clear_settings_cache()
    logger.info("settings.yaml updated via dashboard: %d field(s) changed", len(update_data))

    return _build_response()
