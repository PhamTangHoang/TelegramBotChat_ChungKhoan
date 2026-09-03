from datetime import date, timedelta
from decimal import Decimal

from app.analysis.structure import analyze_structure
from app.domain.schemas import MarketCandle


def candle(day: date, close: float, volume: float = 1000) -> MarketCandle:
    return MarketCandle(
        symbol="FPT",
        exchange="HOSE",
        trading_date=day,
        open=Decimal(str(close - 1)),
        high=Decimal(str(close + 2)),
        low=Decimal(str(close - 2)),
        close=Decimal(str(close)),
        volume=Decimal(str(volume)),
        source="fixture",
        is_final=True,
    )


def test_structure_calculates_vpvr_cpr_support_and_wyckoff_from_ohlcv() -> None:
    start = date(2026, 1, 1)
    candles = [candle(start + timedelta(days=i), 100 + i * 0.5) for i in range(80)]

    result = analyze_structure(candles[:-1], candles[-1])

    assert result.wyckoff_phase == "Markup"
    assert result.vpvr_poc is not None
    assert result.vpvr_hvn is not None
    assert result.vpvr_breakout is not None
    assert result.support_price is not None
    assert result.resistance_price is not None
    assert result.cpr_weekly_top is not None
    assert result.cpr_monthly_top is not None


def test_structure_marks_insufficient_history_without_inventing_levels() -> None:
    start = date(2026, 1, 1)
    candles = [candle(start + timedelta(days=i), 100 + i) for i in range(10)]

    result = analyze_structure(candles[:-1], candles[-1])

    assert result.wyckoff_phase is None
    assert result.pattern_name is None
    assert result.vpvr_poc is None
    assert result.cpr_weekly_top is None
