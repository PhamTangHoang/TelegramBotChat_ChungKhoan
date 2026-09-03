
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import MarketCandle, Symbol
from app.domain.schemas import MarketCandle as MarketCandleInput


def get_or_create_symbol(session: Session, symbol: str, exchange: str) -> Symbol:
    existing = session.scalar(
        select(Symbol).where(Symbol.symbol == symbol, Symbol.exchange == exchange)
    )
    if existing is not None:
        return existing
    created = Symbol(symbol=symbol, exchange=exchange)
    session.add(created)
    session.flush()
    return created


def upsert_intraday_candle(session: Session, candle: MarketCandleInput) -> MarketCandle:
    symbol = get_or_create_symbol(session, candle.symbol, candle.exchange)
    stored = session.scalar(
        select(MarketCandle)
        .where(
            MarketCandle.symbol_id == symbol.id,
            MarketCandle.trading_date == candle.trading_date,
        )
        .with_for_update()
    )
    if stored is None:
        stored = MarketCandle(
            symbol_id=symbol.id,
            trading_date=candle.trading_date,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=int(candle.volume),
            adjusted_close=candle.adjusted_close,
            price_basis=candle.price_basis.value,
            source=candle.source,
            provider_timestamp=candle.provider_timestamp,
            is_final=False,
        )
        session.add(stored)
        session.flush()
        return stored

    if stored.is_final:
        return stored
    stored.high = max(stored.high, candle.high)
    stored.low = min(stored.low, candle.low)
    stored.close = candle.close
    stored.volume = int(candle.volume)
    stored.adjusted_close = candle.adjusted_close
    stored.price_basis = candle.price_basis.value
    stored.source = candle.source
    stored.provider_timestamp = candle.provider_timestamp
    session.flush()
    return stored


def finalize_candle(session: Session, candle: MarketCandleInput) -> MarketCandle:
    symbol = get_or_create_symbol(session, candle.symbol, candle.exchange)
    stored = session.scalar(
        select(MarketCandle)
        .where(
            MarketCandle.symbol_id == symbol.id,
            MarketCandle.trading_date == candle.trading_date,
        )
        .with_for_update()
    )
    if stored is not None and stored.is_final:
        return stored
    if stored is None:
        stored = MarketCandle(symbol_id=symbol.id, trading_date=candle.trading_date)
        session.add(stored)
    stored.open = candle.open
    stored.high = candle.high
    stored.low = candle.low
    stored.close = candle.close
    stored.volume = int(candle.volume)
    stored.adjusted_close = candle.adjusted_close
    stored.price_basis = candle.price_basis.value
    stored.source = candle.source
    stored.provider_timestamp = candle.provider_timestamp
    stored.is_final = True
    session.flush()
    return stored
