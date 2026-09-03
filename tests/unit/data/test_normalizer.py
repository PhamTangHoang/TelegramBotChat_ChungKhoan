from datetime import date, datetime
from decimal import Decimal

import pytest

from app.data.errors import ProviderSchemaError, ProviderSemanticError
from app.data.normalizer import normalize_ohlcv


def test_normalizer_maps_common_provider_columns() -> None:
    rows = [
        {
            "time": "2026-09-03",
            "open": 100,
            "high": 110,
            "low": 95,
            "close": 105,
            "volume": 1000,
        }
    ]

    result = normalize_ohlcv(rows, symbol="fpt", exchange="hose", source="fixture")

    assert len(result) == 1
    assert result[0].symbol == "FPT"
    assert result[0].trading_date == date(2026, 9, 3)
    assert result[0].close == Decimal("105")
    assert result[0].price_basis.value == "RAW_OHLCV"


def test_normalizer_accepts_provider_timestamp_and_adjusted_close() -> None:
    rows = [
        {
            "date": date(2026, 9, 3),
            "open": "100",
            "high": "110",
            "low": "95",
            "close": "105",
            "volume": "1000",
            "adjusted_close": "104.5",
            "provider_timestamp": datetime(2026, 9, 3, 2, 0),
        }
    ]

    result = normalize_ohlcv(rows, symbol="FPT", exchange="HOSE", source="fixture")

    assert result[0].adjusted_close == Decimal("104.5")
    assert result[0].provider_timestamp == datetime(2026, 9, 3, 2, 0)


def test_normalizer_rejects_missing_columns() -> None:
    with pytest.raises(ProviderSchemaError):
        normalize_ohlcv(
            [{"time": "2026-09-03", "open": 100}],
            symbol="FPT",
            exchange="HOSE",
            source="fixture",
        )


def test_normalizer_rejects_unknown_volume_semantics() -> None:
    rows = [
        {
            "time": "2026-09-03",
            "open": 100,
            "high": 110,
            "low": 95,
            "close": 105,
            "volume": 1000,
        }
    ]

    with pytest.raises(ProviderSemanticError):
        normalize_ohlcv(
            rows,
            symbol="FPT",
            exchange="HOSE",
            source="fixture",
            volume_semantics="unknown",
        )


def test_normalizer_rejects_empty_provider_response() -> None:
    with pytest.raises(ProviderSchemaError, match="empty"):
        normalize_ohlcv(
            [],
            symbol="FPT",
            exchange="HOSE",
            source="fixture",
        )
