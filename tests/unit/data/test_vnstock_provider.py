from datetime import date

import pytest

from app.data.errors import NoMarketDataError
from app.data.providers.vnstock import VnstockProvider


class FakeEquity:
    def ohlcv(self, **_: object):
        return [
            {
                "time": "2026-09-03",
                "open": 100,
                "high": 110,
                "low": 95,
                "close": 105,
                "volume": 1000,
            }
        ]


class FakeIndex:
    def ohlcv(self, **_: object):
        return [
            {
                "time": "2026-09-03",
                "open": 1200,
                "high": 1210,
                "low": 1190,
                "close": 1205,
                "volume": 0,
            }
        ]


class FakeClient:
    def equity(self, **_: object):
        return FakeEquity()

    def index(self, **_: object):
        return FakeIndex()


class DuplicateIndex(FakeIndex):
    def ohlcv(self, **_: object):
        return [
            {
                "time": "2026-09-03 07:00:00",
                "open": 1200,
                "high": 1210,
                "low": 1190,
                "close": 1205,
                "volume": 100,
            },
            {
                "time": "2026-09-03 07:00:00",
                "open": 1201,
                "high": 1210,
                "low": 1190,
                "close": 1205,
                "volume": 200,
            },
        ]


class DuplicateIndexClient(FakeClient):
    def index(self, **_: object):
        return DuplicateIndex()


class DuplicateEquity(FakeEquity):
    def ohlcv(self, **_: object):
        return [
            {
                "time": "2026-09-03 07:00:00",
                "open": 100,
                "high": 110,
                "low": 95,
                "close": 105,
                "volume": 1000,
            },
            {
                "time": "2026-09-03 07:00:00",
                "open": 101,
                "high": 111,
                "low": 96,
                "close": 106,
                "volume": 1100,
            },
        ]


class DuplicateEquityClient(FakeClient):
    def equity(self, **_: object):
        return DuplicateEquity()


class EmptyEquity(FakeEquity):
    def ohlcv(self, **_: object):
        raise ValueError("Dữ liệu trống cho mã FEE với interval 1D.")


class EmptyEquityClient(FakeClient):
    def equity(self, **_: object):
        return EmptyEquity()


class InvalidSymbolEquity(FakeEquity):
    def ohlcv(self, **_: object):
        raise ValueError("Invalid symbol. Your symbol format is not recognized!")


class InvalidSymbolClient(FakeClient):
    def equity(self, **_: object):
        return InvalidSymbolEquity()


class FakeListing:
    def symbols_by_exchange(self, **_: object):
        return [
            {"symbol": "ACB", "exchange": "HNX"},
            {"symbol": "FPT", "exchange": "HOSE"},
        ]


class CapturingClient(FakeClient):
    def __init__(self) -> None:
        self.equity_kwargs: dict[str, object] = {}
        self.index_kwargs: dict[str, object] = {}

    def equity(self, **_: object):
        client = self

        class CapturingEquity(FakeEquity):
            def ohlcv(self, **kwargs: object):
                client.equity_kwargs = kwargs
                return super().ohlcv()

        return CapturingEquity()

    def index(self, **_: object):
        client = self

        class CapturingIndex(FakeIndex):
            def ohlcv(self, **kwargs: object):
                client.index_kwargs = kwargs
                return super().ohlcv()

        return CapturingIndex()


def test_vnstock_provider_normalizes_equity_and_index() -> None:
    provider = VnstockProvider(client_factory=lambda: FakeClient())

    candles = provider.get_ohlcv("FPT", date(2026, 9, 1), date(2026, 9, 3), is_final=True)
    indices = provider.get_market_index(
        "VNINDEX", date(2026, 9, 1), date(2026, 9, 3), is_final=True
    )

    assert candles[0].symbol == "FPT"
    assert candles[0].is_final is True
    assert indices[0].index_code == "VNINDEX"


def test_vnstock_provider_keeps_last_duplicate_index_row_per_date() -> None:
    provider = VnstockProvider(client_factory=lambda: DuplicateIndexClient())

    indices = provider.get_market_index(
        "VNINDEX", date(2026, 9, 1), date(2026, 9, 3), is_final=True
    )

    assert len(indices) == 1
    assert indices[0].open == 1201


def test_vnstock_provider_keeps_last_duplicate_equity_row_per_date() -> None:
    provider = VnstockProvider(client_factory=lambda: DuplicateEquityClient())

    candles = provider.get_ohlcv(
        "REE", date(2026, 9, 1), date(2026, 9, 3), is_final=True
    )

    assert len(candles) == 1
    assert candles[0].open == 101
    assert candles[0].close == 106


def test_vnstock_provider_requests_enough_history_for_long_moving_averages() -> None:
    client = CapturingClient()
    provider = VnstockProvider(client_factory=lambda: client)

    provider.get_ohlcv("ACB", date(2025, 1, 1), date(2026, 9, 3))
    provider.get_market_index("VNINDEX", date(2025, 1, 1), date(2026, 9, 3))

    assert client.equity_kwargs["count"] >= 260
    assert client.index_kwargs["count"] >= 260


def test_vnstock_provider_classifies_empty_symbol_data() -> None:
    provider = VnstockProvider(client_factory=lambda: EmptyEquityClient())

    with pytest.raises(NoMarketDataError, match="FEE"):
        provider.get_ohlcv("FEE", date(2026, 9, 1), date(2026, 9, 3))


def test_vnstock_provider_classifies_invalid_symbol_data() -> None:
    provider = VnstockProvider(client_factory=lambda: InvalidSymbolClient())

    with pytest.raises(NoMarketDataError, match="BAD"):
        provider.get_ohlcv("BAD", date(2026, 9, 1), date(2026, 9, 3))


def test_vnstock_provider_resolves_exchange_for_on_demand_symbol() -> None:
    provider = VnstockProvider(
        client_factory=lambda: FakeClient(),
        listing_factory=lambda **_: FakeListing(),
    )

    assert provider.resolve_exchange("ACB") == "HNX"
    assert provider.resolve_exchange("FPT") == "HOSE"
    assert provider.resolve_exchange("UNKNOWN") is None


def test_vnstock_provider_rejects_unknown_symbol_after_listing_preflight() -> None:
    provider = VnstockProvider(
        client_factory=lambda: InvalidSymbolClient(),
        listing_factory=lambda **_: FakeListing(),
    )
    provider.resolve_exchange("UNKNOWN")

    with pytest.raises(NoMarketDataError, match="UNKNOWN"):
        provider.get_ohlcv("UNKNOWN", date(2026, 9, 1), date(2026, 9, 3))
