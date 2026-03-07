"""Historical candle data loader.

Parses CSV files in Binance kline format into ``list[OHLCV]``, with optional
date filtering, resampling, and bar-count capping.

Binance kline CSV columns (headerless or with header):
    open_time, open, high, low, close, volume, close_time,
    quote_volume, count, taker_buy_volume, taker_buy_quote_volume, ignore
"""

from __future__ import annotations

import csv
import logging
from datetime import UTC, datetime
from pathlib import Path

from trading_crew.models.market import OHLCV

logger = logging.getLogger(__name__)

_TIMEFRAME_SECONDS: dict[str, int] = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "8h": 28800,
    "12h": 43200,
    "1d": 86400,
    "1w": 604800,
}


def load_candles_csv(
    path: str | Path,
    symbol: str = "BTC/USDT",
    exchange: str = "binance",
    timeframe: str = "1m",
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    max_bars: int | None = None,
    resample: str | None = None,
) -> list[OHLCV]:
    """Load OHLCV candles from a Binance kline CSV file.

    Args:
        path: Path to the CSV file.
        symbol: Trading pair to stamp on each OHLCV.
        exchange: Exchange name to stamp on each OHLCV.
        timeframe: Timeframe label for the raw candles.
        start: Include only candles on or after this datetime (UTC).
        end: Include only candles on or before this datetime (UTC).
        max_bars: Truncate to at most this many bars after all other filters.
        resample: Aggregate candles to a larger timeframe (e.g. ``"1h"``).

    Returns:
        Sorted list of OHLCV candles.
    """
    filepath = Path(path)
    if not filepath.exists():
        raise FileNotFoundError(f"Candle CSV not found: {filepath}")

    rows = _read_csv(filepath)
    candles = _parse_rows(rows, symbol=symbol, exchange=exchange, timeframe=timeframe)

    if start is not None:
        start_utc = start if start.tzinfo else start.replace(tzinfo=UTC)
        candles = [c for c in candles if c.timestamp >= start_utc]

    if end is not None:
        end_utc = end if end.tzinfo else end.replace(tzinfo=UTC)
        candles = [c for c in candles if c.timestamp <= end_utc]

    candles.sort(key=lambda c: c.timestamp)

    if resample is not None:
        candles = _resample(candles, resample, symbol=symbol, exchange=exchange)

    if max_bars is not None and len(candles) > max_bars:
        candles = candles[:max_bars]

    logger.info(
        "Loaded %d candles from %s (symbol=%s, timeframe=%s)",
        len(candles),
        filepath.name,
        symbol,
        resample or timeframe,
    )
    return candles


def _read_csv(filepath: Path) -> list[list[str]]:
    """Read CSV rows, auto-detecting header vs headerless."""
    rows: list[list[str]] = []
    with open(filepath, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        for row in reader:
            if not row:
                continue
            if row[0].strip().lower() in ("open_time", "timestamp", "date"):
                continue
            rows.append(row)
    return rows


def _parse_rows(
    rows: list[list[str]],
    symbol: str,
    exchange: str,
    timeframe: str,
) -> list[OHLCV]:
    """Parse raw CSV rows into OHLCV objects."""
    candles: list[OHLCV] = []
    for i, row in enumerate(rows):
        if len(row) < 6:
            logger.debug("Skipping malformed row %d (only %d columns)", i, len(row))
            continue
        try:
            open_time_raw = float(row[0])
            if open_time_raw > 1e12:
                ts = datetime.fromtimestamp(open_time_raw / 1000, tz=UTC)
            else:
                ts = datetime.fromtimestamp(open_time_raw, tz=UTC)

            candles.append(
                OHLCV(
                    symbol=symbol,
                    exchange=exchange,
                    timeframe=timeframe,
                    timestamp=ts,
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                )
            )
        except (ValueError, IndexError) as exc:
            logger.debug("Skipping row %d: %s", i, exc)
    return candles


def _resample(
    candles: list[OHLCV],
    target_timeframe: str,
    symbol: str,
    exchange: str,
) -> list[OHLCV]:
    """Aggregate candles into a larger timeframe.

    Uses OHLCV rules: first open, max high, min low, last close, sum volume.
    """
    if target_timeframe not in _TIMEFRAME_SECONDS:
        raise ValueError(
            f"Unknown timeframe {target_timeframe!r}. Supported: {', '.join(_TIMEFRAME_SECONDS)}"
        )

    interval = _TIMEFRAME_SECONDS[target_timeframe]
    if not candles:
        return []

    buckets: dict[datetime, list[OHLCV]] = {}
    for c in candles:
        epoch = int(c.timestamp.timestamp())
        bucket_epoch = epoch - (epoch % interval)
        bucket_ts = datetime.fromtimestamp(bucket_epoch, tz=UTC)
        buckets.setdefault(bucket_ts, []).append(c)

    resampled: list[OHLCV] = []
    for bucket_ts in sorted(buckets):
        group = buckets[bucket_ts]
        resampled.append(
            OHLCV(
                symbol=symbol,
                exchange=exchange,
                timeframe=target_timeframe,
                timestamp=bucket_ts,
                open=group[0].open,
                high=max(c.high for c in group),
                low=min(c.low for c in group),
                close=group[-1].close,
                volume=sum(c.volume for c in group),
            )
        )
    return resampled
