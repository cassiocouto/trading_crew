"""Pluggable trading strategies.

All strategies inherit from ``BaseStrategy`` and implement ``generate_signal()``.
Community contributors add new strategies by creating a new file in this package.

Built-in strategies:
    ema_crossover  — EMA fast/slow crossover (ported from silvia_v2)
    bollinger      — Bollinger Bands mean reversion
    rsi_range      — RSI + price range positioning
    composite      — Ensemble/voting across multiple strategies
"""
