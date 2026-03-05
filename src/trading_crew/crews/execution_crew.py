"""Execution Crew.

Places risk-approved orders and monitors their lifecycle. Runs after
the Strategy Crew has validated signals.

Agents:
  - Executor: Places orders on the exchange (or simulates in paper mode)
  - Monitor: Tracks order status, detects fills, cancels stale orders

Tasks (sequential):
  1. execute_orders → Executor
  2. monitor_orders → Monitor (depends on step 1)
"""

from __future__ import annotations

from crewai import Agent, Crew, Task


class ExecutionCrew:
    """Assembles and runs the Execution Crew.

    Args:
        executor: The Executor agent instance.
        monitor: The Monitor agent instance.
        task_configs: Task definitions from tasks.yaml.
        stale_order_cancel_minutes: Minutes before stale orders are cancelled.
    """

    def __init__(
        self,
        executor: Agent,
        monitor: Agent,
        task_configs: dict[str, dict[str, str]],
        stale_order_cancel_minutes: int = 10,
    ) -> None:
        self._executor = executor
        self._monitor = monitor
        self._task_configs = task_configs
        self._stale_minutes = stale_order_cancel_minutes

    def build(self, *, verbose: bool = False) -> Crew:
        """Build the Crew with its agents and tasks."""
        exec_config = self._task_configs.get("execute_orders", {})
        monitor_config = self._task_configs.get("monitor_orders", {})

        exec_task = Task(
            description=exec_config.get("description", "Execute approved orders"),
            expected_output=exec_config.get("expected_output", "Placed orders"),
            agent=self._executor,
        )

        monitor_task = Task(
            description=monitor_config.get("description", "Monitor open orders").format(
                stale_order_cancel_minutes=self._stale_minutes,
            ),
            expected_output=monitor_config.get("expected_output", "Order status updates"),
            agent=self._monitor,
            context=[exec_task],
        )

        return Crew(
            agents=[self._executor, self._monitor],
            tasks=[exec_task, monitor_task],
            verbose=verbose,
        )
