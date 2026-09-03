from collections.abc import Sequence
from datetime import date
from typing import Protocol

from app.domain.schemas import IndexCandle, MarketCandle


class MarketDataProvider(Protocol):
    def get_ohlcv(
        self, symbol: str, start: date, end: date, *, is_final: bool = False
    ) -> Sequence[MarketCandle]: ...

    def get_market_index(
        self, index_code: str, start: date, end: date, *, is_final: bool = False
    ) -> Sequence[IndexCandle]: ...
