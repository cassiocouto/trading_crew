"""Risk management modules.

Individual risk checks (position sizing, stop-loss, portfolio limits, circuit
breaker) live here. They are orchestrated by ``services.risk_pipeline.RiskPipeline``
which chains them into a full validation flow:

  TradeSignal → confidence filter → CircuitBreaker → PositionSizer
  → StopLoss → PortfolioLimits → ConcentrationLimits → RiskCheckResult

If any stage rejects the signal, the pipeline short-circuits. This module is the
biggest improvement over silvia_v1/v2, where risk management was essentially absent.
"""
