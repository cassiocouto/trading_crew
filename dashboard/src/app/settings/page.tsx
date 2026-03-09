"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle, Info, KeyRound, RotateCcw, Save } from "lucide-react";
import { useSettings, useUpdateSettings } from "@/hooks/useApi";
import type { RiskParamsResponse, SettingsResponse, SettingsUpdate } from "@/types";

export default function SettingsPage() {
  const { data: settings, isLoading } = useSettings();
  const updateSettings = useUpdateSettings();

  const [form, setForm] = useState<Partial<SettingsResponse> | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Initialise form when settings load
  useEffect(() => {
    if (settings && !form) {
      setForm(settings);
    }
  }, [settings, form]);

  const set = <K extends keyof SettingsResponse>(key: K, value: SettingsResponse[K]) => {
    setForm((prev) => prev ? { ...prev, [key]: value } : prev);
    setDirty(true);
    setSaved(false);
  };

  const setRisk = (key: keyof RiskParamsResponse, value: number) => {
    setForm((prev) => {
      if (!prev) return prev;
      const baseRisk: RiskParamsResponse = prev.risk ??
        settings?.risk ?? {
          max_position_size_pct: 10,
          max_portfolio_exposure_pct: 80,
          max_drawdown_pct: 15,
          default_stop_loss_pct: 3,
          risk_per_trade_pct: 2,
          min_confidence: 0.5,
          cooldown_after_loss_seconds: 300,
          min_profit_margin_pct: 0,
        };
      return { ...prev, risk: { ...baseRisk, [key]: value } };
    });
    setDirty(true);
    setSaved(false);
  };

  const reset = () => {
    if (settings) {
      setForm(settings);
      setDirty(false);
      setSaved(false);
    }
  };

  const save = async () => {
    if (!form) return;
    setError(null);
    try {
      // Build a SettingsUpdate payload — exclude read-only / secret / dashboard
      // infrastructure fields that are not accepted by the API.
      const {
        advisory_llm_configured: _llm,
        dashboard_enabled: _de,
        dashboard_host: _dh,
        dashboard_port: _dp,
        dashboard_cors_origins: _dco,
        dashboard_ws_poll_interval_seconds: _dwp,
        ...editable
      } = form as SettingsResponse;
      await updateSettings.mutateAsync(editable as SettingsUpdate);
      setDirty(false);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings.");
    }
  };

  if (isLoading || !form) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-48 animate-pulse rounded bg-gray-200" />
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-40 animate-pulse rounded-xl bg-gray-100" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-16">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Settings</h1>
          <p className="mt-0.5 text-sm text-gray-500">
            Non-secret configuration — saved to{" "}
            <code className="rounded bg-gray-100 px-1 text-xs">settings.yaml</code>. Most changes
            require a bot restart.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {dirty && (
            <button
              onClick={reset}
              className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-600 hover:bg-gray-50"
            >
              <RotateCcw size={14} />
              Reset
            </button>
          )}
          <button
            onClick={save}
            disabled={!dirty || updateSettings.isPending}
            className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            <Save size={14} />
            {updateSettings.isPending ? "Saving…" : "Save Changes"}
          </button>
        </div>
      </div>

      {/* Banners */}
      {saved && (
        <div className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-700">
          <CheckCircle size={16} />
          Settings saved. Most changes take effect on the next bot restart. Use the{" "}
          <a href="/controls" className="underline">
            Controls
          </a>{" "}
          page for live toggles.
        </div>
      )}
      {error && (
        <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          {error}
        </div>
      )}

      {/* Secrets notice */}
      <div className="flex items-start gap-2 rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-700">
        <KeyRound size={15} className="mt-0.5 shrink-0" />
        API keys, tokens, and database URL are managed in your{" "}
        <code className="rounded bg-blue-100 px-1 text-xs">.env</code> file and are never
        stored here.
      </div>

      {/* Section: Trading */}
      <Section title="Trading">
        <SelectField
          label="Trading Mode"
          value={form.trading_mode ?? "paper"}
          options={["paper", "live"]}
          onChange={(v) => set("trading_mode", v)}
        />
        <TextField
          label="Exchange ID"
          value={form.exchange_id ?? "binance"}
          onChange={(v) => set("exchange_id", v)}
          hint="e.g. binance, kraken, bybit"
        />
        <BoolField
          label="Sandbox Mode"
          value={form.exchange_sandbox ?? false}
          onChange={(v) => set("exchange_sandbox", v)}
          hint="Use exchange sandbox/testnet API endpoint"
        />
        <ArrayField
          label="Symbols"
          value={form.symbols ?? []}
          onChange={(v) => set("symbols", v)}
          hint="Trading pairs, one per line (e.g. BTC/USDT)"
        />
        <TextField
          label="Default Timeframe"
          value={form.default_timeframe ?? "1h"}
          onChange={(v) => set("default_timeframe", v)}
          hint="e.g. 1m, 5m, 15m, 1h, 4h, 1d"
        />
        <NumberField
          label="Initial Paper Balance (quote)"
          value={form.initial_balance_quote ?? 10000}
          onChange={(v) => set("initial_balance_quote", v)}
          hint="Starting balance for paper trading only"
          min={1}
        />
      </Section>

      {/* Section: Scheduling */}
      <Section title="Scheduling">
        <NumberField
          label="Loop Interval (seconds)"
          value={form.loop_interval_seconds ?? 900}
          onChange={(v) => set("loop_interval_seconds", v)}
          min={10}
          hint="How often the main trading cycle runs"
        />
        <NumberField
          label="Execution Poll Interval (seconds)"
          value={form.execution_poll_interval_seconds ?? 900}
          onChange={(v) => set("execution_poll_interval_seconds", v)}
          min={10}
          hint="How often open orders are reconciled"
        />
        <NumberField
          label="Stale Order Cancel (minutes)"
          value={form.stale_order_cancel_minutes ?? 10}
          onChange={(v) => set("stale_order_cancel_minutes", v)}
          min={1}
        />
        <NumberField
          label="Stale Partial Fill Cancel (minutes)"
          value={form.stale_partial_fill_cancel_minutes ?? 360}
          onChange={(v) => set("stale_partial_fill_cancel_minutes", v)}
          min={1}
        />
        <NumberField
          label="Balance Sync Interval (seconds)"
          value={form.balance_sync_interval_seconds ?? 300}
          onChange={(v) => set("balance_sync_interval_seconds", v)}
          min={0}
          hint="Live mode only. 0 = disabled"
        />
      </Section>

      {/* Section: Strategy */}
      <Section title="Strategy">
        <BoolField
          label="Ensemble Mode"
          value={form.ensemble_enabled ?? false}
          onChange={(v) => set("ensemble_enabled", v)}
          hint="Require multiple strategies to agree before generating a signal"
        />
        <NumberField
          label="Ensemble Agreement Threshold"
          value={form.ensemble_agreement_threshold ?? 0.5}
          onChange={(v) => set("ensemble_agreement_threshold", v)}
          min={0}
          max={1}
          step={0.05}
        />
        <SelectField
          label="Stop-Loss Method"
          value={form.stop_loss_method ?? "fixed"}
          options={["fixed", "atr"]}
          onChange={(v) => set("stop_loss_method", v)}
        />
        <NumberField
          label="ATR Stop Multiplier"
          value={form.atr_stop_multiplier ?? 2.0}
          onChange={(v) => set("atr_stop_multiplier", v)}
          min={0.1}
          max={10}
          step={0.1}
          hint="Used when stop_loss_method = atr"
        />
      </Section>

      {/* Section: Position Guards */}
      <Section title="Position Guards">
        <BoolField
          label="Anti-Averaging-Down"
          value={form.anti_averaging_down ?? true}
          onChange={(v) => set("anti_averaging_down", v)}
          hint="Reject new BUY when entry is at or below existing stop-loss"
        />
        <SelectField
          label="Sell Guard Mode"
          value={form.sell_guard_mode ?? "break_even"}
          options={["none", "break_even"]}
          onChange={(v) => set("sell_guard_mode", v)}
          hint="break_even: hold until price ≥ most recent BUY break-even"
        />
      </Section>

      {/* Section: Risk Parameters */}
      <Section title="Risk Parameters">
        <NumberField
          label="Max Position Size (%)"
          value={form.risk?.max_position_size_pct ?? 10}
          onChange={(v) => setRisk("max_position_size_pct", v)}
          min={0.1}
          max={100}
          step={0.5}
        />
        <NumberField
          label="Max Portfolio Exposure (%)"
          value={form.risk?.max_portfolio_exposure_pct ?? 80}
          onChange={(v) => setRisk("max_portfolio_exposure_pct", v)}
          min={1}
          max={100}
          step={1}
        />
        <NumberField
          label="Max Drawdown (%) — Circuit Breaker"
          value={form.risk?.max_drawdown_pct ?? 15}
          onChange={(v) => setRisk("max_drawdown_pct", v)}
          min={1}
          max={100}
          step={0.5}
        />
        <NumberField
          label="Default Stop-Loss (%)"
          value={form.risk?.default_stop_loss_pct ?? 3}
          onChange={(v) => setRisk("default_stop_loss_pct", v)}
          min={0.1}
          max={50}
          step={0.1}
        />
        <NumberField
          label="Risk Per Trade (%)"
          value={form.risk?.risk_per_trade_pct ?? 2}
          onChange={(v) => setRisk("risk_per_trade_pct", v)}
          min={0.1}
          max={20}
          step={0.1}
        />
        <NumberField
          label="Min Signal Confidence"
          value={form.risk?.min_confidence ?? 0.5}
          onChange={(v) => setRisk("min_confidence", v)}
          min={0}
          max={1}
          step={0.05}
        />
        <NumberField
          label="Post-Loss Cooldown (seconds)"
          value={form.risk?.cooldown_after_loss_seconds ?? 300}
          onChange={(v) => setRisk("cooldown_after_loss_seconds", v)}
          min={0}
        />
        <NumberField
          label="Min Profit Margin Above Break-Even (%)"
          value={form.risk?.min_profit_margin_pct ?? 0}
          onChange={(v) => setRisk("min_profit_margin_pct", v)}
          min={0}
          max={20}
          step={0.1}
        />
      </Section>

      {/* Section: Market Intelligence */}
      <Section title="Market Intelligence">
        <NumberField
          label="Candle Limit"
          value={form.market_data_candle_limit ?? 120}
          onChange={(v) => set("market_data_candle_limit", v)}
          min={20}
          max={1000}
          hint="Number of candles fetched per cycle"
        />
        <NumberField
          label="Regime Volatility Threshold"
          value={form.market_regime_volatility_threshold ?? 0.03}
          onChange={(v) => set("market_regime_volatility_threshold", v)}
          min={0}
          max={1}
          step={0.005}
        />
        <NumberField
          label="Regime Trend Threshold"
          value={form.market_regime_trend_threshold ?? 0.01}
          onChange={(v) => set("market_regime_trend_threshold", v)}
          min={0}
          max={1}
          step={0.001}
        />
        <BoolField
          label="Sentiment Enrichment"
          value={form.sentiment_enabled ?? false}
          onChange={(v) => set("sentiment_enabled", v)}
        />
        <BoolField
          label="Fear & Greed Index"
          value={form.sentiment_fear_greed_enabled ?? true}
          onChange={(v) => set("sentiment_fear_greed_enabled", v)}
          hint="Requires sentiment_enabled = true"
        />
        <NumberField
          label="Fear & Greed Weight"
          value={form.sentiment_fear_greed_weight ?? 1.0}
          onChange={(v) => set("sentiment_fear_greed_weight", v)}
          min={0}
          step={0.1}
        />
      </Section>

      {/* Section: Advisory Crew */}
      <Section title="Advisory Crew">
        {!form.advisory_llm_configured && (
          <div className="col-span-2 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-700">
            <Info size={15} className="mt-0.5 shrink-0" />
            No LLM API key detected. Set{" "}
            <code className="rounded bg-amber-100 px-1 text-xs">OPENAI_API_KEY</code> in{" "}
            <code className="rounded bg-amber-100 px-1 text-xs">.env</code> for the advisory crew
            to function.
          </div>
        )}
        <BoolField
          label="Advisory Enabled"
          value={form.advisory_enabled ?? true}
          onChange={(v) => set("advisory_enabled", v)}
        />
        <NumberField
          label="Activation Threshold"
          value={form.advisory_activation_threshold ?? 0.6}
          onChange={(v) => set("advisory_activation_threshold", v)}
          min={0}
          max={1}
          step={0.05}
          hint="Uncertainty score required to trigger advisory"
        />
        <NumberField
          label="Estimated Tokens Per Activation"
          value={form.advisory_estimated_tokens ?? 4000}
          onChange={(v) => set("advisory_estimated_tokens", v)}
          min={0}
        />
        <BoolField
          label="Daily Token Budget"
          value={form.daily_token_budget_enabled ?? true}
          onChange={(v) => set("daily_token_budget_enabled", v)}
        />
        <NumberField
          label="Daily Token Budget Limit"
          value={form.daily_token_budget_tokens ?? 600000}
          onChange={(v) => set("daily_token_budget_tokens", v)}
          min={1}
        />
        <SelectField
          label="Budget Degrade Mode"
          value={form.token_budget_degrade_mode ?? "normal"}
          options={["normal", "budget_stop"]}
          onChange={(v) => set("token_budget_degrade_mode", v)}
          hint="budget_stop: disable advisory when limit is hit"
        />
        <div className="col-span-2">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-400">
            Uncertainty Score Weights
          </p>
          <div className="grid grid-cols-2 gap-3">
            {(
              [
                ["uncertainty_weight_volatile_regime", "Volatile Regime"],
                ["uncertainty_weight_sentiment_extreme", "Sentiment Extreme"],
                ["uncertainty_weight_low_sentiment_confidence", "Low Sentiment Confidence"],
                ["uncertainty_weight_strategy_disagreement", "Strategy Disagreement"],
                ["uncertainty_weight_drawdown_proximity", "Drawdown Proximity"],
                ["uncertainty_weight_regime_change", "Regime Change"],
              ] as [keyof SettingsResponse, string][]
            ).map(([key, label]) => (
              <NumberField
                key={key}
                label={label}
                value={(form[key] as number) ?? 0.3}
                onChange={(v) => set(key, v as SettingsResponse[typeof key])}
                min={0}
                max={1}
                step={0.05}
              />
            ))}
          </div>
        </div>
      </Section>

      {/* Section: Logging */}
      <Section title="Logging & Debug">
        <SelectField
          label="Log Level"
          value={form.log_level ?? "INFO"}
          options={["DEBUG", "INFO", "WARNING", "ERROR"]}
          onChange={(v) => set("log_level", v)}
        />
        <BoolField
          label="CrewAI Verbose"
          value={form.crewai_verbose ?? false}
          onChange={(v) => set("crewai_verbose", v)}
          hint="Show rich CrewAI agent output in the terminal"
        />
      </Section>

      {/* Footer save bar */}
      {dirty && (
        <div className="fixed bottom-0 left-52 right-0 flex items-center justify-between border-t border-gray-200 bg-white px-6 py-3 shadow-md">
          <span className="text-sm text-gray-500">You have unsaved changes.</span>
          <div className="flex gap-3">
            <button
              onClick={reset}
              className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
            >
              Discard
            </button>
            <button
              onClick={save}
              disabled={updateSettings.isPending}
              className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              <Save size={14} />
              {updateSettings.isPending ? "Saving…" : "Save Changes"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Reusable form field components
// ---------------------------------------------------------------------------

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-400">{title}</h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">{children}</div>
    </div>
  );
}

function TextField({
  label,
  value,
  onChange,
  hint,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  hint?: string;
}) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-gray-700">{label}</label>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400"
      />
      {hint && <p className="mt-1 text-xs text-gray-400">{hint}</p>}
    </div>
  );
}

function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
  hint,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  hint?: string;
}) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-gray-700">{label}</label>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => {
          const v = parseFloat(e.target.value);
          if (!Number.isNaN(v)) onChange(v);
        }}
        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400"
      />
      {hint && <p className="mt-1 text-xs text-gray-400">{hint}</p>}
    </div>
  );
}

function BoolField({
  label,
  value,
  onChange,
  hint,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
  hint?: string;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <p className="text-sm font-medium text-gray-700">{label}</p>
        {hint && <p className="mt-0.5 text-xs text-gray-400">{hint}</p>}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={value}
        onClick={() => onChange(!value)}
        className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none ${
          value ? "bg-indigo-600" : "bg-gray-200"
        }`}
      >
        <span
          className={`inline-block size-5 transform rounded-full bg-white shadow transition-transform ${
            value ? "translate-x-5" : "translate-x-0"
          }`}
        />
      </button>
    </div>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
  hint,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
  hint?: string;
}) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-gray-700">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400"
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
      {hint && <p className="mt-1 text-xs text-gray-400">{hint}</p>}
    </div>
  );
}

function ArrayField({
  label,
  value,
  onChange,
  hint,
}: {
  label: string;
  value: string[];
  onChange: (v: string[]) => void;
  hint?: string;
}) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-gray-700">{label}</label>
      <textarea
        rows={3}
        value={value.join("\n")}
        onChange={(e) =>
          onChange(
            e.target.value
              .split("\n")
              .map((s) => s.trim())
              .filter(Boolean)
          )
        }
        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400"
      />
      {hint && <p className="mt-1 text-xs text-gray-400">{hint}</p>}
    </div>
  );
}
