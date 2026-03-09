"""Market data REST endpoints — OHLCV candles and ticker snapshots."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query

from trading_crew.api.deps import get_db
from trading_crew.api.schemas import OHLCVBar, SymbolTickerResponse
from trading_crew.config.settings import get_settings
from trading_crew.db.models import OHLCVRecord, TickerRecord
from trading_crew.db.session import get_session

if TYPE_CHECKING:
    from trading_crew.services.database_service import DatabaseService

router = APIRouter(tags=["market"])


@router.get("/symbols", response_model=list[SymbolTickerResponse])
def get_symbols(db: DatabaseService = Depends(get_db)) -> list[SymbolTickerResponse]:
    """Return configured symbols with their latest ticker prices."""
    from sqlalchemy import select

    settings = get_settings()

    result: list[SymbolTickerResponse] = []
    with get_session(db._engine) as session:
        for symbol in settings.symbols:
            row = session.execute(
                select(TickerRecord)
                .where(TickerRecord.symbol == symbol)
                .order_by(TickerRecord.timestamp.desc())
                .limit(1)
            ).scalar_one_or_none()

            result.append(
                SymbolTickerResponse(
                    symbol=symbol,
                    last_price=row.last if row else None,
                    bid=row.bid if row else None,
                    ask=row.ask if row else None,
                    volume_24h=row.volume_24h if row else None,
                    timestamp=row.timestamp.isoformat() if row else None,
                )
            )
    return result


@router.get("/ohlcv", response_model=list[OHLCVBar])
def get_ohlcv(
    symbol: str = Query(..., description="Trading pair, e.g. BTC/USDT"),
    timeframe: str = Query("1h", description="Candle timeframe, e.g. 1h, 4h, 1d"),
    limit: int = Query(120, ge=1, le=500, description="Number of candles to return"),
    db: DatabaseService = Depends(get_db),
) -> list[OHLCVBar]:
    """Return OHLCV candlestick bars for a symbol/timeframe from the database.

    Returns an empty list if no data has been collected yet for the symbol.
    Timestamps are returned as Unix seconds for lightweight-charts compatibility.
    """
    from sqlalchemy import select

    settings = get_settings()

    # Normalise symbol — accept both "BTC/USDT" and "BTCUSDT"
    exchange_id = settings.exchange_id

    with get_session(db._engine) as session:
        rows = (
            session.execute(
                select(OHLCVRecord)
                .where(OHLCVRecord.symbol == symbol)
                .where(OHLCVRecord.exchange == exchange_id)
                .where(OHLCVRecord.timeframe == timeframe)
                .order_by(OHLCVRecord.timestamp.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )

    # Reverse so oldest bar is first (chart expects chronological order)
    bars = list(reversed(rows))
    return [
        OHLCVBar(
            timestamp=int(row.timestamp.timestamp()),
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
        )
        for row in bars
    ]
