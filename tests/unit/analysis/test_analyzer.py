from datetime import date, timedelta
from decimal import Decimal

from app.analysis.analyzer import TechnicalAnalyzer
from app.domain.schemas import IndexCandle, MarketCandle
from app.market.calendar import HOSECalendar


def candle(day: date, close: int, volume: int = 1000, is_final: bool = True) -> MarketCandle:
    return MarketCandle(
        symbol="FPT",
        exchange="HOSE",
        trading_date=day,
        open=Decimal(close - 1),
        high=Decimal(close + 1),
        low=Decimal(close - 2),
        close=Decimal(close),
        volume=Decimal(volume),
        source="fixture",
        is_final=is_final,
    )


def index_candle(day: date, close: int, is_final: bool = True) -> IndexCandle:
    return IndexCandle(
        index_code="VNINDEX",
        trading_date=day,
        open=Decimal(close - 1),
        high=Decimal(close + 1),
        low=Decimal(close - 2),
        close=Decimal(close),
        source="fixture",
        is_final=is_final,
    )


def test_analyzer_appends_current_developing_candle_and_emits_raw_snapshot() -> None:
    start = date(2026, 7, 1)
    history = [candle(start + timedelta(days=i), 100 + i) for i in range(50)]
    current_day = start + timedelta(days=50)
    current = candle(current_day, 180, volume=500, is_final=False)
    index_history = [index_candle(start + timedelta(days=i), 1000 + i) for i in range(50)]
    current_index = index_candle(current_day, 1050, is_final=False)

    snapshot = TechnicalAnalyzer(HOSECalendar()).analyze(
        history=history,
        current=current,
        index_history=index_history,
        current_index=current_index,
        elapsed_minutes=50,
    )

    assert snapshot.price == Decimal("180")
    assert snapshot.price_basis.value == "RAW_OHLCV"
    assert snapshot.ma20 is not None
    assert snapshot.ma50 is not None
    assert snapshot.rsi14 is not None
    assert snapshot.macd_histogram is not None
    assert snapshot.atr14 is not None
    assert snapshot.relative_return is not None
    assert snapshot.is_final is False
