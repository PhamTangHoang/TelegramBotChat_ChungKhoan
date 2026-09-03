from datetime import date, datetime
from decimal import Decimal
from importlib.util import find_spec

import pytest

from app.chart.chart_engine import ChartEngine, ChartError
from app.domain.schemas import MarketCandle


def candle(day: int, close: str) -> MarketCandle:
    price = Decimal(close)
    return MarketCandle(
        symbol="FPT",
        exchange="HOSE",
        trading_date=date(2026, 1, day),
        open=price - 1,
        high=price + 2,
        low=price - 2,
        close=price,
        volume=1000,
        source="test",
        is_final=True,
    )


@pytest.mark.skipif(
    find_spec("matplotlib") is None or find_spec("mplfinance") is None,
    reason="chart runtime dependencies are installed in the Docker image",
)
def test_chart_returns_png_bytes_and_closes_figures() -> None:
    result = ChartEngine().render(
        [candle(day, str(100 + day)) for day in range(1, 6)],
        symbol="FPT",
        as_of=datetime(2026, 1, 5, 3, 0),
        is_final=True,
    )

    assert result.startswith(b"\x89PNG\r\n\x1a\n")


def test_chart_requires_multiple_observations() -> None:
    with pytest.raises(ChartError, match="two candles"):
        ChartEngine().render(
            [candle(1, "100")],
            symbol="FPT",
            as_of=datetime(2026, 1, 1),
            is_final=False,
        )
