from datetime import date

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
