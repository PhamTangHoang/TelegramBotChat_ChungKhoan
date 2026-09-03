from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database.models import Base
from app.database.repositories.candle_repository import (
    finalize_candle,
    finalize_index_candle,
    get_finalized_history,
    get_index_candles,
    get_market_candles,
    upsert_index_candle,
    upsert_intraday_candle,
)
from app.domain.schemas import IndexCandle, MarketCandle


def market(day: int, *, final: bool = True) -> MarketCandle:
    return MarketCandle(
        symbol="FPT",
        exchange="HOSE",
        trading_date=date(2026, 1, day),
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("105"),
        volume=1000,
        source="test",
        is_final=final,
    )


def index(day: int, *, final: bool = True) -> IndexCandle:
    return IndexCandle(
        index_code="VNINDEX",
        trading_date=date(2026, 1, day),
        open=Decimal("1200"),
        high=Decimal("1210"),
        low=Decimal("1190"),
        close=Decimal("1205"),
        source="test",
        is_final=final,
    )


def session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def test_read_repositories_return_validated_inputs_and_final_history() -> None:
    db = session()
    finalize_candle(db, market(1))
    upsert_intraday_candle(db, market(2, final=False))
    upsert_index_candle(db, index(1))
    finalize_index_candle(db, index(2, final=False))
    db.commit()

    assert len(get_market_candles(db, symbol="FPT", exchange="HOSE")) == 2
    assert (
        len(
            get_finalized_history(
                db,
                symbol="FPT",
                exchange="HOSE",
                before=date(2026, 1, 3),
            )
        )
        == 1
    )
    assert len(get_index_candles(db, index_code="VNINDEX")) == 2
