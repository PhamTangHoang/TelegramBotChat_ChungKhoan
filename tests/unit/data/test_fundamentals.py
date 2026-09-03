from types import SimpleNamespace

from app.data.providers.fundamentals import VnstockFundamentalProvider


class FakeFrame:
    columns = ["item", "item_id", "current", "previous", "older"]

    def __init__(self, records: list[dict[str, object]]) -> None:
        self.records = records

    def to_dict(self, *, orient: str) -> list[dict[str, object]]:
        assert orient == "records"
        return self.records


class FakeFinance:
    def __init__(self, **_: object) -> None:
        self.table = FakeFrame(
            [
                {"item": "Revenue growth", "item_id": "net_revenue", "current": 12, "previous": 8},
                {
                    "item": "Profit growth",
                    "item_id": "profit_after_tax_for_shareholders_of_the_parent_company",
                    "current": 15,
                    "previous": 10,
                },
                {"item": "EPS", "item_id": "trailing_eps", "current": 110, "previous": 100},
                {"item": "ROE", "item_id": "roe_trailling", "current": 18, "previous": 17},
                {"item": "PE", "item_id": "pe_ratio", "current": 12, "previous": 13},
                {"item": "PB", "item_id": "pb_ratio", "current": 2, "previous": 2.2},
            ]
        )

    def ratio(self, **_: object) -> FakeFrame:
        return self.table


def test_fundamental_provider_normalizes_ratio_snapshot() -> None:
    provider = VnstockFundamentalProvider(
        source="kbs", finance_factory=lambda **kwargs: FakeFinance(**kwargs)
    )

    result = provider.get_snapshot("FPT")

    assert result.revenue_growth == 12.0
    assert result.earnings_growth == 15.0
    assert result.eps_growth == 10.0
    assert result.roe == 18.0
    assert result.pe == 12.0
    assert result.pb == 2.0
    assert result.historical_pe == 12.5
    assert result.historical_pb == 2.1
