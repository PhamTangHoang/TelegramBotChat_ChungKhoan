
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import MarketCandle, MarketIndex, Symbol
from app.domain.schemas import IndexCandle as IndexCandleInput
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


def upsert_index_candle(session: Session, candle: IndexCandleInput) -> MarketIndex:
    stored = session.scalar(
        select(MarketIndex).where(
            MarketIndex.index_code == candle.index_code,
            MarketIndex.trading_date == candle.trading_date,
        )
    )
    if stored is None:
        stored = MarketIndex(
            index_code=candle.index_code,
            trading_date=candle.trading_date,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            source=candle.source,
            provider_timestamp=candle.provider_timestamp,
            is_final=candle.is_final,
        )
        session.add(stored)
    elif not stored.is_final:
        stored.open = candle.open
        stored.high = max(stored.high, candle.high)
        stored.low = min(stored.low, candle.low)
        stored.close = candle.close
        stored.source = candle.source
        stored.provider_timestamp = candle.provider_timestamp
        stored.is_final = candle.is_final
    session.flush()
    return stored


def finalize_index_candle(session: Session, candle: IndexCandleInput) -> MarketIndex:
    candle = candle.model_copy(update={"is_final": True})
    return upsert_index_candle(session, candle)


def get_market_candles(
    session: Session,
    *,
    symbol: str,
    exchange: str,
    start: date | None = None,
    end: date | None = None,
) -> list[MarketCandleInput]:
    query = (
        select(MarketCandle, Symbol)
        .join(Symbol, MarketCandle.symbol_id == Symbol.id)
        .where(Symbol.symbol == symbol.upper(), Symbol.exchange == exchange.upper())
        .order_by(MarketCandle.trading_date)
    )
    if start is not None:
        query = query.where(MarketCandle.trading_date >= start)
    if end is not None:
        query = query.where(MarketCandle.trading_date <= end)
    return [_market_input(row, symbol_row) for row, symbol_row in session.execute(query)]


def get_market_candle_with_metadata(
    session: Session,
    *,
    symbol: str,
    exchange: str,
    trading_date: date,
) -> tuple[MarketCandleInput, object] | None:
    row = session.execute(
        select(MarketCandle, Symbol)
        .join(Symbol, MarketCandle.symbol_id == Symbol.id)
        .where(
            Symbol.symbol == symbol.upper(),
            Symbol.exchange == exchange.upper(),
            MarketCandle.trading_date == trading_date,
        )
    ).first()
    if row is None:
        return None
    candle, symbol_row = row
    return _market_input(candle, symbol_row), candle.updated_at


def get_finalized_history(
    session: Session,
    *,
    symbol: str,
    exchange: str,
    before: date,
    limit: int = 50,
) -> list[MarketCandleInput]:
    query = (
        select(MarketCandle, Symbol)
        .join(Symbol, MarketCandle.symbol_id == Symbol.id)
        .where(
            Symbol.symbol == symbol.upper(),
            Symbol.exchange == exchange.upper(),
            MarketCandle.trading_date < before,
            MarketCandle.is_final.is_(True),
        )
        .order_by(MarketCandle.trading_date.desc())
        .limit(limit)
    )
    rows = [_market_input(row, symbol_row) for row, symbol_row in session.execute(query)]
    return list(reversed(rows))


def get_index_candles(
    session: Session,
    *,
    index_code: str,
    start: date | None = None,
    end: date | None = None,
) -> list[IndexCandleInput]:
    query = (
        select(MarketIndex)
        .where(MarketIndex.index_code == index_code.upper())
        .order_by(MarketIndex.trading_date)
    )
    if start is not None:
        query = query.where(MarketIndex.trading_date >= start)
    if end is not None:
        query = query.where(MarketIndex.trading_date <= end)
    return [_index_input(row) for row in session.scalars(query)]


def get_index_candle_with_metadata(
    session: Session,
    *,
    index_code: str,
    trading_date: date,
) -> tuple[IndexCandleInput, object] | None:
    row = session.scalar(
        select(MarketIndex).where(
            MarketIndex.index_code == index_code.upper(),
            MarketIndex.trading_date == trading_date,
        )
    )
    if row is None:
        return None
    return _index_input(row), row.updated_at


def _market_input(row: MarketCandle, symbol: Symbol) -> MarketCandleInput:
    return MarketCandleInput(
        symbol=symbol.symbol,
        exchange=symbol.exchange,
        trading_date=row.trading_date,
        open=row.open,
        high=row.high,
        low=row.low,
        close=row.close,
        volume=row.volume,
        adjusted_close=row.adjusted_close,
        source=row.source,
        provider_timestamp=row.provider_timestamp,
        is_final=row.is_final,
    )


def _index_input(row: MarketIndex) -> IndexCandleInput:
    return IndexCandleInput(
        index_code=row.index_code,
        trading_date=row.trading_date,
        open=row.open,
        high=row.high,
        low=row.low,
        close=row.close,
        source=row.source,
        provider_timestamp=row.provider_timestamp,
        is_final=row.is_final,
    )
