# Writing a Strategy

Trading strategies are the most common community contribution. This guide
walks through creating a new strategy from scratch.

## The BaseStrategy Interface

All strategies inherit from `BaseStrategy` and implement one method:

```python
from trading_crew.strategies.base import BaseStrategy
from trading_crew.models.market import MarketAnalysis
from trading_crew.models.signal import TradeSignal

class MyStrategy(BaseStrategy):
    name = "my_strategy"

    def generate_signal(self, analysis: MarketAnalysis) -> TradeSignal | None:
        # Your logic here
        ...
```

## Available Indicators

The `MarketAnalysis` object contains pre-computed indicators from the
`TechnicalAnalyzer`:

| Indicator | Key | Description |
|-----------|-----|-------------|
| Fast EMA | `ema_fast` | 12-period EMA |
| Slow EMA | `ema_slow` | 50-period EMA |
| RSI | `rsi_14` | 14-period RSI |
| BB Upper | `bb_upper` | Upper Bollinger Band |
| BB Middle | `bb_middle` | Middle Bollinger Band (SMA 20) |
| BB Lower | `bb_lower` | Lower Bollinger Band |
| MACD Line | `macd_line` | MACD line (12-EMA minus 26-EMA) |
| MACD Signal | `macd_signal` | 9-period EMA of MACD line |
| MACD Histogram | `macd_histogram` | MACD line minus signal line |
| ATR | `atr_14` | 14-period Average True Range |
| Range High | `range_high` | Recent high |
| Range Low | `range_low` | Recent low |

Access them with `analysis.get_indicator("ema_fast")`.

## Interaction with the Uncertainty Scorer

Your strategy's signals feed into the `UncertaintyScorer`. When multiple
strategies disagree on direction for a symbol, the **strategy disagreement**
factor increases the uncertainty score, which can trigger the advisory crew.

This means:

- Strategies that produce clear, confident signals in calm markets help keep
  uncertainty low (no advisory activation, no LLM cost).
- Strategies that are highly sensitive or noisy may increase advisory
  activations. Consider using appropriate confidence values and filtering out
  weak signals by returning `None`.

The full vote breakdown (each strategy's signal per symbol) is captured in
the `StrategyEvaluation` and passed to the uncertainty scorer.

## Example: MACD Strategy

```python
from trading_crew.strategies.base import BaseStrategy
from trading_crew.models.market import MarketAnalysis
from trading_crew.models.signal import SignalStrength, SignalType, TradeSignal


class MACDStrategy(BaseStrategy):
    name = "macd"

    def generate_signal(self, analysis: MarketAnalysis) -> TradeSignal | None:
        macd = analysis.get_indicator("macd_line")
        macd_signal = analysis.get_indicator("macd_signal")

        if macd is None or macd_signal is None:
            return None

        # Bullish crossover
        if macd > macd_signal and macd > 0:
            return TradeSignal(
                symbol=analysis.symbol,
                exchange=analysis.exchange,
                signal_type=SignalType.BUY,
                strength=SignalStrength.MODERATE,
                confidence=0.65,
                strategy_name=self.name,
                entry_price=analysis.current_price,
                reason=f"MACD bullish crossover: {macd:.2f} > {macd_signal:.2f}",
            )

        return None
```

## Testing Your Strategy

1. Add unit tests in `tests/unit/strategies/`:

```python
def test_macd_buy_signal():
    analysis = MarketAnalysis(
        symbol="BTC/USDT",
        exchange="binance",
        timestamp=datetime.utcnow(),
        current_price=60000,
        indicators={"macd_line": 150, "macd_signal": 100},
    )
    strategy = MACDStrategy()
    signal = strategy.generate_signal(analysis)
    assert signal is not None
    assert signal.signal_type == SignalType.BUY
```

2. Run: `make test-unit`
3. Validate in paper-trading mode before submitting a PR.

## Submitting

1. Create your strategy file in `src/trading_crew/strategies/`
2. Add tests
3. Open a PR with the "New Strategy" label
