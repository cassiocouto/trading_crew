"""Market Intelligence Crew.

Fetches market data and computes technical analysis. This crew runs first
in each trading cycle, providing the data foundation for strategy evaluation.

Agents:
  - Sentinel: Fetches tickers and OHLCV candles
  - Analyst: Computes technical indicators
  - Sentiment: Gathers market sentiment (optional, Phase 2b)

Tasks (sequential):
  1. fetch_market_data → Sentinel
  2. analyze_market → Analyst (depends on step 1)
  3. analyze_sentiment → Sentiment (independent, can run in parallel later)
"""

from __future__ import annotations

from crewai import Agent, Crew, Task


class MarketCrew:
    """Assembles and runs the Market Intelligence Crew.

    Args:
        sentinel: The Sentinel agent instance.
        analyst: The Analyst agent instance.
        sentiment: The Sentiment agent instance (optional).
        task_configs: Task definitions from tasks.yaml.
        symbols: Trading pairs to analyze.
        exchange_id: Exchange identifier.
        timeframe: OHLCV timeframe.
    """

    def __init__(
        self,
        sentinel: Agent,
        analyst: Agent,
        sentiment: Agent | None,
        task_configs: dict[str, dict[str, str]],
        symbols: list[str],
        exchange_id: str,
        timeframe: str = "1h",
    ) -> None:
        self._sentinel = sentinel
        self._analyst = analyst
        self._sentiment = sentiment
        self._task_configs = task_configs
        self._symbols = symbols
        self._exchange_id = exchange_id
        self._timeframe = timeframe

    def build(self, *, verbose: bool = False) -> Crew:
        """Build the Crew with its agents and tasks."""
        fetch_config = self._task_configs.get("fetch_market_data", {})
        analyze_config = self._task_configs.get("analyze_market", {})

        symbols_str = ", ".join(self._symbols)

        fetch_task = Task(
            description=fetch_config.get("description", "Fetch market data").format(
                symbols=symbols_str,
                exchange_id=self._exchange_id,
                timeframe=self._timeframe,
            ),
            expected_output=fetch_config.get("expected_output", "Market data"),
            agent=self._sentinel,
        )

        analyze_task = Task(
            description=analyze_config.get("description", "Analyze market data"),
            expected_output=analyze_config.get("expected_output", "Market analysis"),
            agent=self._analyst,
            context=[fetch_task],
        )

        tasks = [fetch_task, analyze_task]
        agents = [self._sentinel, self._analyst]

        if self._sentiment:
            sentiment_config = self._task_configs.get("analyze_sentiment", {})
            sentiment_task = Task(
                description=sentiment_config.get("description", "Analyze sentiment"),
                expected_output=sentiment_config.get("expected_output", "Sentiment data"),
                agent=self._sentiment,
            )
            tasks.append(sentiment_task)
            agents.append(self._sentiment)

        return Crew(
            agents=agents,
            tasks=tasks,
            verbose=verbose,
        )
