"""Risk management pipeline.

Every trade signal passes through this pipeline before execution:
  TradeSignal → PositionSizer → StopLoss → PortfolioLimits → CircuitBreaker → OrderRequest

If any stage rejects the signal, the order is not placed. This module is the
biggest improvement over silvia_v1/v2, where risk management was essentially absent.
"""
