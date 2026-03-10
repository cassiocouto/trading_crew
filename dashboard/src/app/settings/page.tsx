"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle, Info, KeyRound, RotateCcw, Save } from "lucide-react";
import { HelpTooltip } from "@/components/HelpTooltip";
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
        <div className="h-8 w-48 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-40 animate-pulse rounded-xl bg-gray-100 dark:bg-gray-800" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-16">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Settings</h1>
          <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
            Non-secret configuration — saved to{" "}
            <code className="rounded bg-gray-100 px-1 text-xs dark:bg-gray-800">settings.yaml</code>. Most changes
            require a bot restart.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {dirty && (
            <button
              onClick={reset}
              className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-400 dark:hover:bg-gray-800"
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
        <div className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-700 dark:border-green-800 dark:bg-green-900/20 dark:text-green-300">
          <CheckCircle size={16} />
          Settings saved. Most changes take effect on the next bot restart. Use the{" "}
          <a href="/controls" className="underline">
            Controls
          </a>{" "}
          page for live toggles.
        </div>
      )}
      {error && (
        <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          {error}
        </div>
      )}

      {/* Secrets notice */}
      <div className="flex items-start gap-2 rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-700 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-300">
        <KeyRound size={15} className="mt-0.5 shrink-0" />
        API keys, tokens, and database URL are managed in your{" "}
        <code className="rounded bg-blue-100 px-1 text-xs dark:bg-blue-900/40">.env</code> file and are never
        stored here.
      </div>

      {/* Section: Trading */}
      <Section title="Trading">
        <SelectField
          label="Trading Mode"
          value={form.trading_mode ?? "paper"}
          options={["paper", "live"]}
          onChange={(v) => set("trading_mode", v)}
          tooltip="paper = simulated trading with a virtual balance, no real orders placed. live = real orders sent to the exchange. Always test in paper mode first."
        />
        <TextField
          label="Exchange ID"
          value={form.exchange_id ?? "binance"}
          onChange={(v) => set("exchange_id", v)}
          hint="e.g. binance, kraken, bybit"
          tooltip="CCXT exchange identifier (lowercase). Must match exactly. Common values: binance, kraken, bybit, coinbasepro."
        />
        <BoolField
          label="Sandbox Mode"
          value={form.exchange_sandbox ?? false}
          onChange={(v) => set("exchange_sandbox", v)}
          hint="Use exchange sandbox/testnet API endpoint"
          tooltip="Connects to the exchange's test environment. Orders are simulated but the API behaves like production — safe for testing live mode without risking funds."
        />
        <ArrayField
          label="Symbols"
          value={form.symbols ?? []}
          onChange={(v) => set("symbols", v)}
          hint="Trading pairs, one per line (e.g. BTC/USDT)"
          tooltip="Pairs to trade, in BASE/QUOTE format supported by your exchange. The bot tracks all symbols simultaneously each cycle."
        />
        <TextField
          label="Default Timeframe"
          value={form.default_timeframe ?? "1h"}
          onChange={(v) => set("default_timeframe", v)}
          hint="e.g. 1m, 5m, 15m, 1h, 4h, 1d"
          tooltip="Candle interval for market analysis. Shorter intervals generate more signals but also more noise. Longer intervals are smoother but react more slowly."
        />
        <NumberField
          label="Initial Paper Balance (quote)"
          value={form.initial_balance_quote ?? 10000}
          onChange={(v) => set("initial_balance_quote", v)}
          hint="Starting balance for paper trading only"
          min={1}
          tooltip="Virtual starting balance in quote currency (e.g. USDT) for paper trading. Only applied when the paper portfolio is first created or reset."
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
          tooltip="Frequency of the analysis → signal → order cycle. 900 s = every 15 minutes. Lower values increase exchange API call frequency."
        />
        <NumberField
          label="Execution Poll Interval (seconds)"
          value={form.execution_poll_interval_seconds ?? 900}
          onChange={(v) => set("execution_poll_interval_seconds", v)}
          min={10}
          hint="How often open orders are reconciled"
          tooltip="How often the bot checks the exchange to see if pending orders have been filled or cancelled. Independent of the main analysis cycle."
        />
        <NumberField
          label="Stale Order Cancel (minutes)"
          value={form.stale_order_cancel_minutes ?? 10}
          onChange={(v) => set("stale_order_cancel_minutes", v)}
          min={1}
          tooltip="Unfilled limit orders older than this many minutes are automatically cancelled to free up reserved capital."
        />
        <NumberField
          label="Stale Partial Fill Cancel (minutes)"
          value={form.stale_partial_fill_cancel_minutes ?? 360}
          onChange={(v) => set("stale_partial_fill_cancel_minutes", v)}
          min={1}
          tooltip="Orders that have been partially filled and have not fully completed within this many minutes are cancelled. The partial fill is kept as an open position."
        />
        <NumberField
          label="Balance Sync Interval (seconds)"
          value={form.balance_sync_interval_seconds ?? 300}
          onChange={(v) => set("balance_sync_interval_seconds", v)}
          min={0}
          hint="Live mode only. 0 = disabled"
          tooltip="How often the real exchange balance is fetched to reconcile the internal portfolio state. Useful if you also trade manually on the same account. Live mode only; set 0 to disable."
        />
      </Section>

      {/* Section: Strategy */}
      <Section title="Strategy">
        <BoolField
          label="Ensemble Mode"
          value={form.ensemble_enabled ?? false}
          onChange={(v) => set("ensemble_enabled", v)}
          hint="Require multiple strategies to agree before generating a signal"
          tooltip="When on, all strategies vote per symbol and a signal is only emitted when enough of them agree. Reduces false signals but may miss faster opportunities. When off, each strategy fires independently."
        />
        <NumberField
          label="Ensemble Agreement Threshold"
          value={form.ensemble_agreement_threshold ?? 0.5}
          onChange={(v) => set("ensemble_agreement_threshold", v)}
          min={0}
          max={1}
          step={0.05}
          tooltip="Fraction of active strategies that must agree for a consensus signal (0.5 = majority). Only applies when Ensemble Mode is on. Higher = more conservative, fewer signals."
        />
        <SelectField
          label="Stop-Loss Method"
          value={form.stop_loss_method ?? "fixed"}
          options={["fixed", "atr"]}
          onChange={(v) => set("stop_loss_method", v)}
          tooltip="fixed = stop at a fixed percentage below entry (see Default Stop-Loss %). atr = stop at a multiple of Average True Range below entry — automatically widens during volatile markets and tightens during calm ones."
        />
        <NumberField
          label="ATR Stop Multiplier"
          value={form.atr_stop_multiplier ?? 2.0}
          onChange={(v) => set("atr_stop_multiplier", v)}
          min={0.1}
          max={10}
          step={0.1}
          hint="Used when stop_loss_method = atr"
          tooltip="Multiplied by ATR(14) to determine the stop-loss distance from entry. A higher value gives wider stops that are less likely to be triggered by normal volatility, but larger losses when they are."
        />
      </Section>

      {/* Section: Position Guards */}
      <Section title="Position Guards">
        <BoolField
          label="Anti-Averaging-Down"
          value={form.anti_averaging_down ?? true}
          onChange={(v) => set("anti_averaging_down", v)}
          hint="Reject new BUY when entry is at or below existing stop-loss"
          tooltip="Prevents the bot from buying more of an asset when the current price is at or below the existing position's stop-loss price. Protects against compounding losses on a falling trade."
        />
        <SelectField
          label="Sell Guard Mode"
          value={form.sell_guard_mode ?? "break_even"}
          options={["none", "break_even"]}
          onChange={(v) => set("sell_guard_mode", v)}
          hint="break_even: hold until price ≥ most recent BUY break-even"
          tooltip="none = sell immediately when a SELL signal fires. break_even = only execute a sell when price is at or above the break-even price of the most recent buy, preventing realising a loss. The min_profit_margin setting adds an extra buffer on top."
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
          tooltip="Maximum size of a single position as a percentage of total portfolio value. Caps how much capital is staked on one trade regardless of signal confidence."
        />
        <NumberField
          label="Max Portfolio Exposure (%)"
          value={form.risk?.max_portfolio_exposure_pct ?? 80}
          onChange={(v) => setRisk("max_portfolio_exposure_pct", v)}
          min={1}
          max={100}
          step={1}
          tooltip="Maximum percentage of total portfolio that may be in open positions simultaneously. New buys are blocked when this limit is reached, regardless of available balance."
        />
        <NumberField
          label="Max Drawdown (%) — Circuit Breaker"
          value={form.risk?.max_drawdown_pct ?? 15}
          onChange={(v) => setRisk("max_drawdown_pct", v)}
          min={1}
          max={100}
          step={0.5}
          tooltip="If the portfolio drops by more than this % from its peak value, all new orders are blocked until manually re-enabled on the Controls page. Acts as an emergency brake."
        />
        <NumberField
          label="Default Stop-Loss (%)"
          value={form.risk?.default_stop_loss_pct ?? 3}
          onChange={(v) => setRisk("default_stop_loss_pct", v)}
          min={0.1}
          max={50}
          step={0.1}
          tooltip="Distance below entry price at which a stop-loss order is placed when using the fixed stop-loss method. E.g. 3 means stop at 3% below buy price."
        />
        <NumberField
          label="Risk Per Trade (%)"
          value={form.risk?.risk_per_trade_pct ?? 2}
          onChange={(v) => setRisk("risk_per_trade_pct", v)}
          min={0.1}
          max={20}
          step={0.1}
          tooltip="Maximum percentage of portfolio risked on a single trade. Position size is calculated so that if the stop-loss is hit, the loss equals exactly this percentage of the portfolio."
        />
        <NumberField
          label="Min Signal Confidence"
          value={form.risk?.min_confidence ?? 0.5}
          onChange={(v) => setRisk("min_confidence", v)}
          min={0}
          max={1}
          step={0.05}
          tooltip="Signals below this confidence threshold (0–1) are rejected by the risk pipeline before reaching the order stage. Raising this reduces trade frequency but improves signal quality."
        />
        <NumberField
          label="Post-Loss Cooldown (seconds)"
          value={form.risk?.cooldown_after_loss_seconds ?? 300}
          onChange={(v) => setRisk("cooldown_after_loss_seconds", v)}
          min={0}
          tooltip="After a stop-loss is triggered, the bot waits this many seconds before placing new orders for the same symbol. Prevents immediately re-entering a losing trade. Set 0 to disable."
        />
        <NumberField
          label="Min Profit Margin Above Break-Even (%)"
          value={form.risk?.min_profit_margin_pct ?? 0}
          onChange={(v) => setRisk("min_profit_margin_pct", v)}
          min={0}
          max={20}
          step={0.1}
          tooltip="When Sell Guard Mode is break_even, this adds an extra buffer: only sell when price is at least this % above break-even. E.g. 0.5 means price must be 0.5% above break-even before selling."
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
          tooltip="How many historical candles are fetched per symbol on each cycle. More candles improve indicator accuracy (especially slow indicators like EMA 50 and MACD) at the cost of higher memory and API usage."
        />
        <NumberField
          label="Regime Volatility Threshold"
          value={form.market_regime_volatility_threshold ?? 0.03}
          onChange={(v) => set("market_regime_volatility_threshold", v)}
          min={0}
          max={1}
          step={0.005}
          tooltip="ATR(14)/price ratio above which the market is classified as 'volatile'. A volatile regime can trigger the advisory crew and affects ATR-based stop sizing. Default 0.03 = 3% ATR."
        />
        <NumberField
          label="Regime Trend Threshold"
          value={form.market_regime_trend_threshold ?? 0.01}
          onChange={(v) => set("market_regime_trend_threshold", v)}
          min={0}
          max={1}
          step={0.001}
          tooltip="EMA-spread/price ratio above which the market is classified as 'trending' (if not already volatile). EMA spread = |EMA fast − EMA slow|. Default 0.01 = 1% spread."
        />
        <BoolField
          label="Sentiment Enrichment"
          value={form.sentiment_enabled ?? false}
          onChange={(v) => set("sentiment_enabled", v)}
          tooltip="Fetch and incorporate market sentiment data (Fear & Greed index, etc.) into the advisory crew's analysis context. Adds a small HTTP request per cycle."
        />
        <BoolField
          label="Fear & Greed Index"
          value={form.sentiment_fear_greed_enabled ?? true}
          onChange={(v) => set("sentiment_fear_greed_enabled", v)}
          hint="Requires sentiment_enabled = true"
          tooltip="Include the Crypto Fear & Greed Index (alternative.me) in the sentiment data passed to the advisory crew. Only active when Sentiment Enrichment is on."
        />
        <NumberField
          label="Fear & Greed Weight"
          value={form.sentiment_fear_greed_weight ?? 1.0}
          onChange={(v) => set("sentiment_fear_greed_weight", v)}
          min={0}
          step={0.1}
          tooltip="Relative weight of the Fear & Greed index when blending multiple sentiment sources. Higher = more influence on the overall sentiment score."
        />
      </Section>

      {/* Section: Advisory Crew */}
      <Section title="Advisory Crew">
        {!form.advisory_llm_configured && (
          <div className="col-span-2 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
            <Info size={15} className="mt-0.5 shrink-0" />
            No LLM API key detected. Set{" "}
            <code className="rounded bg-amber-100 px-1 text-xs dark:bg-amber-900/40">OPENAI_API_KEY</code> in{" "}
            <code className="rounded bg-amber-100 px-1 text-xs dark:bg-amber-900/40">.env</code> for the advisory crew
            to function.
          </div>
        )}
        <BoolField
          label="Advisory Enabled"
          value={form.advisory_enabled ?? true}
          onChange={(v) => set("advisory_enabled", v)}
          tooltip="Allow the LLM-based advisory crew to run. When enabled it activates automatically whenever the uncertainty score exceeds the Activation Threshold. Requires a valid LLM API key in .env."
        />
        <NumberField
          label="Activation Threshold"
          value={form.advisory_activation_threshold ?? 0.6}
          onChange={(v) => set("advisory_activation_threshold", v)}
          min={0}
          max={1}
          step={0.05}
          hint="Uncertainty score required to trigger advisory"
          tooltip="Uncertainty score (0–1) that triggers the advisory crew. Lower values mean the crew runs more often (higher cost). Higher values mean it only activates in genuinely high-uncertainty situations. Changes take effect on the next cycle without a restart."
        />
        <NumberField
          label="Estimated Tokens Per Activation"
          value={form.advisory_estimated_tokens ?? 4000}
          onChange={(v) => set("advisory_estimated_tokens", v)}
          min={0}
          tooltip="Approximate number of tokens consumed per advisory crew activation. Used to forecast daily token spend against the budget limit. Adjust based on observed real usage."
        />
        <BoolField
          label="Daily Token Budget"
          value={form.daily_token_budget_enabled ?? true}
          onChange={(v) => set("daily_token_budget_enabled", v)}
          tooltip="Enable a daily spending cap on advisory crew token usage. Resets at midnight UTC. Prevents runaway costs if the uncertainty score triggers advisory frequently."
        />
        <NumberField
          label="Daily Token Budget Limit"
          value={form.daily_token_budget_tokens ?? 600000}
          onChange={(v) => set("daily_token_budget_tokens", v)}
          min={1}
          tooltip="Maximum tokens the advisory crew may consume per calendar day across all activations. What happens when exceeded depends on Budget Degrade Mode."
        />
        <SelectField
          label="Budget Degrade Mode"
          value={form.token_budget_degrade_mode ?? "normal"}
          options={["normal", "budget_stop"]}
          onChange={(v) => set("token_budget_degrade_mode", v)}
          hint="budget_stop: disable advisory when limit is hit"
          tooltip="normal = advisory continues even after the daily limit is reached (logs a warning). budget_stop = advisory is fully disabled for the rest of the day once the limit is hit."
        />
        <div className="col-span-2">
          <p className="mb-1 flex items-center text-xs font-medium uppercase tracking-wide text-gray-400 dark:text-gray-500">
            Uncertainty Score Weights
            <HelpTooltip text="Each cycle, six market factors are each multiplied by their weight and summed. The result is clamped to [0–1] to produce the uncertainty score. The default weights sum to 1.5 (not 1.0) — this is intentional: multiple factors firing together push the score up aggressively, while a single factor alone cannot reach the default threshold of 0.6. Higher weight = that factor triggers the advisory more readily." />
          </p>
          <div className="grid grid-cols-2 gap-3">
            {(
              [
                ["uncertainty_weight_volatile_regime", "Volatile Regime", "Derived from price data. Computed as ATR(14) divided by current price — a purely mathematical measure of how large recent candles are relative to price. The raw value is the fraction of tracked symbols currently above the volatility threshold. A value of 1.0 means every symbol is in a volatile regime this cycle."],
                ["uncertainty_weight_sentiment_extreme", "Sentiment Extreme", "Derived from the Crypto Fear & Greed Index (alternative.me), a daily public index built from volatility, market momentum, social media volume, surveys, Bitcoin dominance, and Google Trends. Fires as a binary signal (0 or 1) when the absolute sentiment score is ≥ 0.5 — meaning the market is either very fearful or very greedy, both of which historically precede sharp reversals. Only active when Sentiment Enrichment is enabled."],
                ["uncertainty_weight_low_sentiment_confidence", "Low Sentiment Confidence", "Derived from the same sentiment data source as Sentiment Extreme. Fires as a binary signal (0 or 1) when the confidence in the sentiment reading is low (≤ 0.5). Low confidence typically means fewer data points were available or sources disagreed. A low-confidence sentiment score is unreliable input, making the situation more uncertain. Only active when Sentiment Enrichment is enabled."],
                ["uncertainty_weight_strategy_disagreement", "Strategy Disagreement", "Derived from the strategy votes generated this cycle using technical indicators (EMA, Bollinger Bands, RSI, MACD). For each symbol, the raw value is 1 minus the fraction of votes held by the dominant faction (buy, sell, or hold). A value of 0 means all strategies agreed; 1 means votes were perfectly split. The final raw value is the average across all tracked symbols."],
                ["uncertainty_weight_drawdown_proximity", "Drawdown Proximity", "Derived from internal portfolio accounting. Computed as current drawdown percentage divided by the circuit-breaker limit (max_drawdown_pct). A value of 0 means the portfolio is at its peak; 1 means drawdown equals the limit and a halt is imminent. This factor rises smoothly as losses accumulate, adding pressure to the score before an actual halt occurs."],
                ["uncertainty_weight_regime_change", "Regime Change", "Derived from price data. The market regime (trending, ranging, or volatile) is classified each cycle using EMA spread and ATR ratios. This factor is the fraction of symbols that changed regime compared to the previous cycle. A value of 0 means all symbols stayed in the same regime; 1 means every symbol shifted. The first cycle always contributes 0 (no previous state to compare)."],
              ] as [keyof SettingsResponse, string, string][]
            ).map(([key, label, tip]) => (
              <NumberField
                key={key}
                label={label}
                value={(form[key] as number) ?? 0.3}
                onChange={(v) => set(key, v as SettingsResponse[typeof key])}
                min={0}
                max={1}
                step={0.05}
                tooltip={tip}
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
          tooltip="Verbosity of the bot's log output. DEBUG includes every indicator value and order decision. INFO is recommended for normal operation. WARNING/ERROR reduce noise in production."
        />
        <BoolField
          label="CrewAI Verbose"
          value={form.crewai_verbose ?? false}
          onChange={(v) => set("crewai_verbose", v)}
          hint="Show rich CrewAI agent output in the terminal"
          tooltip="Enables the full CrewAI agent thought process and tool call output in the terminal. Useful for debugging advisory crew behaviour. Can be very noisy — only enable when investigating an advisory issue."
        />
      </Section>

      {/* Footer save bar */}
      {dirty && (
        <div className="fixed bottom-0 left-52 right-0 flex items-center justify-between border-t border-gray-200 bg-white px-6 py-3 shadow-md dark:border-gray-700 dark:bg-gray-900">
          <span className="text-sm text-gray-500 dark:text-gray-400">You have unsaved changes.</span>
          <div className="flex gap-3">
            <button
              onClick={reset}
              className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-400 dark:hover:bg-gray-800"
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
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-900">
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">{title}</h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">{children}</div>
    </div>
  );
}

function TextField({
  label,
  value,
  onChange,
  hint,
  tooltip,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  hint?: string;
  tooltip?: string;
}) {
  return (
    <div>
      <label className="mb-1 flex items-center text-sm font-medium text-gray-700 dark:text-gray-300">
        {label}
        {tooltip && <HelpTooltip text={tooltip} />}
      </label>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
      />
      {hint && <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">{hint}</p>}
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
  tooltip,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  hint?: string;
  tooltip?: string;
}) {
  return (
    <div>
      <label className="mb-1 flex items-center text-sm font-medium text-gray-700 dark:text-gray-300">
        {label}
        {tooltip && <HelpTooltip text={tooltip} />}
      </label>
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
        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
      />
      {hint && <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">{hint}</p>}
    </div>
  );
}

function BoolField({
  label,
  value,
  onChange,
  hint,
  tooltip,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
  hint?: string;
  tooltip?: string;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <p className="flex items-center text-sm font-medium text-gray-700 dark:text-gray-300">
          {label}
          {tooltip && <HelpTooltip text={tooltip} />}
        </p>
        {hint && <p className="mt-0.5 text-xs text-gray-400 dark:text-gray-500">{hint}</p>}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={value}
        onClick={() => onChange(!value)}
        className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none ${
          value ? "bg-indigo-600" : "bg-gray-200 dark:bg-gray-600"
        }`}
      >
        <span
          className={`inline-block size-5 transform rounded-full bg-white shadow transition-transform dark:bg-gray-200 ${
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
  tooltip,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
  hint?: string;
  tooltip?: string;
}) {
  return (
    <div>
      <label className="mb-1 flex items-center text-sm font-medium text-gray-700 dark:text-gray-300">
        {label}
        {tooltip && <HelpTooltip text={tooltip} />}
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
      {hint && <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">{hint}</p>}
    </div>
  );
}

function ArrayField({
  label,
  value,
  onChange,
  hint,
  tooltip,
}: {
  label: string;
  value: string[];
  onChange: (v: string[]) => void;
  hint?: string;
  tooltip?: string;
}) {
  return (
    <div>
      <label className="mb-1 flex items-center text-sm font-medium text-gray-700 dark:text-gray-300">
        {label}
        {tooltip && <HelpTooltip text={tooltip} />}
      </label>
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
        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
      />
      {hint && <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">{hint}</p>}
    </div>
  );
}
