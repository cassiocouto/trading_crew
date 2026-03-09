"""Atomic reader/writer for the runtime control flags file.

``runtime.yaml`` is read by the bot each cycle and written by the dashboard
API.  Atomic writes (write-to-tmp then os.replace) prevent corrupted reads
when both processes access the file concurrently.

A threading lock serialises writes within a single process (the API server).
The bot only ever reads this file, so no lock is needed on the read path.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import TypedDict

import yaml

logger = logging.getLogger(__name__)

_RUNTIME_YAML: Path = Path(__file__).resolve().parent / "runtime.yaml"


_write_lock = threading.Lock()


class RuntimeFlags(TypedDict):
    """Current runtime control state."""

    execution_paused: bool
    advisory_paused: bool


def read() -> RuntimeFlags:
    """Read runtime flags from disk, bootstrapping the file if absent.

    Returns:
        A ``RuntimeFlags`` dict with current toggle state.
    """
    if not _RUNTIME_YAML.exists():
        _bootstrap()

    try:
        raw = yaml.safe_load(_RUNTIME_YAML.read_text(encoding="utf-8")) or {}
        return RuntimeFlags(
            execution_paused=bool(raw.get("execution_paused", False)),
            advisory_paused=bool(raw.get("advisory_paused", False)),
        )
    except Exception as exc:
        logger.warning("Failed to read runtime.yaml (%s) — using defaults", exc)
        return RuntimeFlags(execution_paused=False, advisory_paused=False)


def write(flags: RuntimeFlags) -> None:
    """Atomically write runtime flags to disk.

    Uses write-to-temp-file + ``os.replace()`` so readers never observe a
    partially written file.

    Args:
        flags: Updated ``RuntimeFlags`` dict to persist.
    """
    tmp = _RUNTIME_YAML.with_suffix(".tmp.yaml")
    content = (
        "# Trading Crew — Runtime Control Flags\n"
        "# Managed by the dashboard. Do NOT commit.\n\n"
        f"execution_paused: {str(flags['execution_paused']).lower()}\n"
        f"advisory_paused: {str(flags['advisory_paused']).lower()}\n"
    )
    with _write_lock:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, _RUNTIME_YAML)
    logger.debug("runtime.yaml updated: %s", dict(flags))


def _bootstrap() -> None:
    """Create runtime.yaml with safe defaults if it does not exist."""
    try:
        write(RuntimeFlags(execution_paused=False, advisory_paused=False))
        logger.info("Bootstrapped runtime.yaml at %s", _RUNTIME_YAML)
    except Exception as exc:
        logger.warning("Could not bootstrap runtime.yaml: %s", exc)
