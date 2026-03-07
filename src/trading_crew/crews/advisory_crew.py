"""Advisory Crew — condition-triggered trading advisor.

A single CrewAI crew that reviews the deterministic pipeline's output when
the uncertainty score exceeds the activation threshold.  Returns structured
``AdvisoryResult`` directives (vetoes, confidence adjustments, stop-loss
tightening, etc.) that the deterministic pipeline re-derives into final
order requests.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any

from crewai import Agent, Crew, Task

from trading_crew.models.advisory import (
    AdjustmentAction,
    AdvisoryAdjustment,
    AdvisoryResult,
)

logger = logging.getLogger(__name__)


def _safe_format(template: str, **kwargs: str) -> str:
    """Format a template, leaving unknown placeholders intact."""
    mapping: dict[str, str] = defaultdict(lambda: "{unknown}", kwargs)
    return template.format_map(mapping)


class AdvisoryCrew:
    """Assembles and runs the Advisory Crew.

    Args:
        context_advisor: Market Context Advisor agent.
        risk_advisor: Risk Advisor agent.
        sentiment_advisor: Optional Sentiment Advisor agent.
        task_configs: Task definitions from tasks.yaml.
    """

    def __init__(
        self,
        context_advisor: Agent,
        risk_advisor: Agent,
        sentiment_advisor: Agent | None = None,
        task_configs: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self._context_advisor = context_advisor
        self._risk_advisor = risk_advisor
        self._sentiment_advisor = sentiment_advisor
        self._task_configs = task_configs or {}

    def build(self, context_text: str, *, verbose: bool = False) -> Crew:
        """Build the crew with structured context injected into task descriptions.

        Args:
            context_text: Pre-formatted text summarizing the deterministic
                pipeline output (analyses, signals, risk results, portfolio
                state, uncertainty factors).
        """
        review_config = self._task_configs.get("review_trading_proposal", {})
        risk_config = self._task_configs.get("assess_risk_adjustments", {})

        agents = [self._context_advisor, self._risk_advisor]
        review_context: list[Task] = []

        if self._sentiment_advisor is not None:
            sentiment_config = self._task_configs.get("interpret_sentiment", {})
            sentiment_task = Task(
                description=_safe_format(
                    sentiment_config.get(
                        "description",
                        "Interpret sentiment and news context.",
                    ),
                    context=context_text,
                ),
                expected_output=sentiment_config.get(
                    "expected_output",
                    "Sentiment interpretation text.",
                ),
                agent=self._sentiment_advisor,
            )
            agents.append(self._sentiment_advisor)
            review_context = [sentiment_task]

        review_task = Task(
            description=_safe_format(
                review_config.get(
                    "description",
                    "Review the trading proposal and recommend adjustments.",
                ),
                context=context_text,
            ),
            expected_output=review_config.get(
                "expected_output",
                "A JSON list of advisory adjustments.",
            ),
            agent=self._context_advisor,
            context=review_context or None,
        )

        risk_task = Task(
            description=_safe_format(
                risk_config.get(
                    "description",
                    "Assess risk adjustments for the current proposal.",
                ),
                context=context_text,
            ),
            expected_output=risk_config.get(
                "expected_output",
                "A JSON object with adjustments, summary, and uncertainty_score.",
            ),
            agent=self._risk_advisor,
            context=[review_task],
        )

        tasks: list[Task] = []
        if self._sentiment_advisor is not None:
            tasks.append(sentiment_task)
        tasks.extend([review_task, risk_task])

        return Crew(agents=agents, tasks=tasks, verbose=verbose)

    async def run(
        self,
        context_text: str,
        uncertainty_score: float,
        *,
        verbose: bool = False,
    ) -> AdvisoryResult:
        """Build the crew and kick off execution, returning a parsed AdvisoryResult."""
        crew = self.build(context_text, verbose=verbose)
        raw_output = await crew.kickoff_async()
        raw_text = getattr(raw_output, "raw", None) or str(raw_output)

        return _parse_advisory_output(raw_text, uncertainty_score)


def _parse_advisory_output(raw: str, uncertainty_score: float) -> AdvisoryResult:
    """Best-effort parse of crew output into an AdvisoryResult."""
    try:
        data: Any = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Advisory crew returned non-JSON output; treating as summary-only")
        return AdvisoryResult(summary=raw, uncertainty_score=uncertainty_score)

    if isinstance(data, dict):
        return _parse_dict_output(data, uncertainty_score)
    if isinstance(data, list):
        adjustments = [_parse_adjustment(item) for item in data if isinstance(item, dict)]
        return AdvisoryResult(
            adjustments=[a for a in adjustments if a is not None],
            summary="",
            uncertainty_score=uncertainty_score,
        )

    return AdvisoryResult(summary=str(data), uncertainty_score=uncertainty_score)


def _parse_dict_output(data: dict[str, Any], uncertainty_score: float) -> AdvisoryResult:
    raw_adjustments = data.get("adjustments", [])
    adjustments = [_parse_adjustment(item) for item in raw_adjustments if isinstance(item, dict)]
    return AdvisoryResult(
        adjustments=[a for a in adjustments if a is not None],
        summary=data.get("summary", ""),
        uncertainty_score=uncertainty_score,
    )


def _parse_adjustment(item: dict[str, Any]) -> AdvisoryAdjustment | None:
    action_str = item.get("action")
    if action_str is None:
        return None
    try:
        action = AdjustmentAction(action_str)
    except ValueError:
        logger.warning("Unknown advisory action: %s", action_str)
        return None
    return AdvisoryAdjustment(
        action=action,
        symbol=item.get("symbol"),
        reason=item.get("reason", ""),
        params=item.get("params", {}),
    )
