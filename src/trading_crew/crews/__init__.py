"""CrewAI Crew definitions.

Each crew wires together a set of agents and tasks to accomplish a specific
phase of the trading pipeline:

- MarketCrew: Fetch and analyze market data
- StrategyCrew: Generate and risk-validate trade signals
- ExecutionCrew: Place and monitor orders
"""
