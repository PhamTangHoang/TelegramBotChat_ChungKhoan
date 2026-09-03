from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database.models import Base, MarketCandle
from app.database.repositories.candle_repository import (
    finalize_candle,
    upsert_intraday_candle,
)
from app.domain.schemas import MarketCandle as MarketCandleInput


def make_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def make_candle(**overrides: object) -> MarketCandleInput:
    data: dict[str, object] = {
        "symbol": "FPT",
        "exchange": "HOSE",
        "trading_date": date(2026, 9, 3),
        "open": Decimal("100"),
        "high": Decimal("105"),
        "low": Decimal("99"),
        "close": Decimal("104"),
        "volume": Decimal("1000"),
        "source": "fixture",
        "provider_timestamp": datetime(2026, 9, 3, 2, 0),
        "is_final": False,
    }
    data.update(overrides)
    return MarketCandleInput.model_validate(data)


def test_intraday_upsert_keeps_open_and_accumulates_range() -> None:
    with make_session() as session:
        upsert_intraday_candle(session, make_candle())
        upsert_intraday_candle(
            session,
            make_candle(
                open=Decimal("101"),
                high=Decimal("110"),
                low=Decimal("95"),
                close=Decimal("108"),
                volume=Decimal("1500"),
            ),
        )
        session.commit()

        rows = session.scalars(select(MarketCandle)).all()

    assert len(rows) == 1
    assert rows[0].open == Decimal("100.000000")
    assert rows[0].high == Decimal("110.000000")
    assert rows[0].low == Decimal("95.000000")
    assert rows[0].close == Decimal("108.000000")
    assert rows[0].volume == 1500


def test_final_candle_cannot_be_overwritten_by_intraday_path() -> None:
    with make_session() as session:
        upsert_intraday_candle(session, make_candle())
        finalize_candle(
            session,
            make_candle(high=Decimal("115"), close=Decimal("113"), volume=Decimal("2000")),
        )
        upsert_intraday_candle(
            session,
            make_candle(high=Decimal("130"), close=Decimal("129"), volume=Decimal("9999")),
        )
        session.commit()

        row = session.scalar(select(MarketCandle))

    assert row is not None
    assert row.is_final is True
    assert row.high == Decimal("115.000000")
    assert row.close == Decimal("113.000000")
    assert row.volume == 2000
