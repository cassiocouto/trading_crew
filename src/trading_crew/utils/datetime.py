"""Datetime parsing helpers."""

from __future__ import annotations

from datetime import UTC, datetime


def parse_iso_utc(value: str) -> datetime:
    """Parse ISO timestamp and normalize to UTC."""
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
