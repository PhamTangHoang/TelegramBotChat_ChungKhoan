from collections.abc import Sequence
from datetime import datetime, time
from decimal import Decimal

from app.analysis.indicators import atr, macd, project_volume_ratio, rsi_wilder, sma
from app.analysis.relative_strength import relative_return
from app.domain.enums import PriceBasis
from app.domain.schemas import IndexCandle, IndicatorSnapshot, MarketCandle
from app.market.calendar import ExchangeCalendar


class TechnicalAnalyzer:
    def __init__(self, calendar: ExchangeCalendar) -> None:
        self.calendar = calendar

    def analyze(
        self,
        *,
        history: Sequence[MarketCandle],
        current: MarketCandle,
        index_history: Sequence[IndexCandle],
        current_index: IndexCandle,
        elapsed_minutes: int | None = None,
        as_of: datetime | None = None,
    ) -> IndicatorSnapshot:
        finalized = list(history)
        if len(finalized) < 50 or any(not candle.is_final for candle in finalized):
            raise ValueError("at least 50 finalized historical candles are required")
        if any(candle.trading_date >= current.trading_date for candle in finalized):
            raise ValueError("historical candles must precede current observation")
        if current.price_basis != PriceBasis.RAW_OHLCV:
            raise ValueError("live MVP analyzer requires RAW_OHLCV")

        closes = [float(candle.close) for candle in finalized] + [float(current.close)]
        highs = [float(candle.high) for candle in finalized] + [float(current.high)]
        lows = [float(candle.low) for candle in finalized] + [float(current.low)]
        volumes = [float(candle.volume) for candle in finalized]

        ma20 = sma(closes, 20)[-1]
        ma50 = sma(closes, 50)[-1]
        rsi14 = rsi_wilder(closes, 14)[-1]
        macd_line, signal_line, histogram = macd(closes)
        atr14 = atr(highs, lows, closes, 14)[-1]

        index_by_date = {candle.trading_date: float(candle.close) for candle in index_history}
        index_by_date[current_index.trading_date] = float(current_index.close)
        stock_dates = [candle.trading_date for candle in finalized] + [current.trading_date]
        aligned_index = [index_by_date.get(trading_date) for trading_date in stock_dates]
        rs = None
        if all(value is not None for value in aligned_index):
            rs = relative_return(
                closes, [value for value in aligned_index if value is not None], 20
            )

        actual_elapsed = (
            elapsed_minutes
            if elapsed_minutes is not None
            else self.calendar.elapsed_trading_minutes(as_of or _fallback_as_of(current))
        )
        average_volume = sum(volumes[-20:]) / 20
        volume_ratio = project_volume_ratio(
            float(current.volume),
            elapsed_minutes=actual_elapsed,
            total_minutes=self.calendar.total_regular_trading_minutes(current.trading_date),
            average_volume=average_volume,
        )
        return IndicatorSnapshot(
            price=Decimal(current.close),
            ma20=ma20,
            ma50=ma50,
            rsi14=rsi14,
            macd=macd_line[-1],
            macd_signal=signal_line[-1],
            macd_histogram=histogram[-1],
            atr14=atr14,
            volume_ratio_projected=volume_ratio,
            elapsed_trading_minutes=actual_elapsed,
            relative_return=rs,
            as_of=as_of or _fallback_as_of(current),
            is_final=current.is_final,
            price_basis=PriceBasis.RAW_OHLCV,
        )


def _fallback_as_of(candle: MarketCandle) -> datetime:
    if candle.provider_timestamp is not None:
        return candle.provider_timestamp
    return datetime.combine(candle.trading_date, time(0, 0))
