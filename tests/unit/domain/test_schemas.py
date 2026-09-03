from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.enums import PriceBasis
from app.domain.schemas import MarketCandle


def valid_candle(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "symbol": "fpt",
        "exchange": "hose",
        "trading_date": date(2026, 9, 3),
        "open": Decimal("100"),
        "high": Decimal("110"),
        "low": Decimal("95"),
        "close": Decimal("105"),
        "volume": Decimal("1000"),
        "price_basis": PriceBasis.RAW_OHLCV,
        "source": "fixture",
        "is_final": False,
    }
    values.update(overrides)
    return values


def test_market_candle_normalizes_identity_fields() -> None:
    candle = MarketCandle.model_validate(valid_candle())

    assert candle.symbol == "FPT"
    assert candle.exchange == "HOSE"


@pytest.mark.parametrize(
    "overrides",
    [
        {"high": Decimal("90")},
        {"low": Decimal("111")},
        {"close": Decimal("111")},
        {"volume": Decimal("-1")},
    ],
)
def test_market_candle_rejects_invalid_ohlcv(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MarketCandle.model_validate(valid_candle(**overrides))
