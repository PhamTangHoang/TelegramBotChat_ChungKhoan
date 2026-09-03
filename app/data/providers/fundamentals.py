from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from math import isfinite
from statistics import mean
from typing import Any

from app.data.errors import FundamentalDataError


@dataclass(frozen=True)
class FundamentalSnapshot:
    revenue_growth: float | None = None
    earnings_growth: float | None = None
    eps_growth: float | None = None
    roe: float | None = None
    pe: float | None = None
    pb: float | None = None
    historical_pe: float | None = None
    historical_pb: float | None = None
    data_source: str = "vnstock_finance_ratio"


class VnstockFundamentalProvider:
    """Normalizes vnstock's ratio report without making financial assumptions."""

    def __init__(
        self,
        *,
        source: str = "kbs",
        finance_factory: Callable[..., Any] | None = None,
    ) -> None:
        normalized_source = source.strip().lower()
        if normalized_source not in {"kbs", "vci"}:
            raise ValueError("vnstock source must be kbs or vci")
        self.source = normalized_source
        self._finance_factory = finance_factory or self._default_finance

    @staticmethod
    def _default_finance(**kwargs: Any) -> Any:
        try:
            from vnstock import Finance
        except ImportError as exc:
            raise FundamentalDataError("vnstock Finance is not installed") from exc
        return Finance(**kwargs)

    def get_snapshot(self, symbol: str) -> FundamentalSnapshot:
        try:
            finance = self._finance_factory(
                source=self.source,
                symbol=symbol,
                period="quarter",
                get_all=True,
                show_log=False,
            )
            table = finance.ratio(orient="report")
            rows = _records(table)
        except FundamentalDataError:
            raise
        except Exception as exc:
            raise FundamentalDataError(f"fundamental data unavailable for {symbol}") from exc
        if not rows:
            raise FundamentalDataError(f"fundamental data unavailable for {symbol}")

        values = _index_rows(rows)
        trailing_eps = values.get("trailing_eps", [])
        return FundamentalSnapshot(
            revenue_growth=_first(values.get("net_revenue", [])),
            earnings_growth=_first(
                values.get("profit_after_tax_for_shareholders_of_the_parent_company", [])
            ),
            eps_growth=_growth(trailing_eps),
            roe=_first(values.get("roe_trailling", []) or values.get("roe", [])),
            pe=_first(values.get("pe_ratio", [])),
            pb=_first(values.get("pb_ratio", [])),
            historical_pe=_positive_mean(values.get("pe_ratio", [])),
            historical_pb=_positive_mean(values.get("pb_ratio", [])),
        )


def _records(table: Any) -> list[Mapping[str, Any]]:
    if hasattr(table, "to_dict"):
        table = table.to_dict(orient="records")
    if not isinstance(table, list) or not all(isinstance(row, Mapping) for row in table):
        raise FundamentalDataError("fundamental provider response must be tabular")
    return table


def _index_rows(rows: list[Mapping[str, Any]]) -> dict[str, list[float]]:
    indexed: dict[str, list[float]] = {}
    for row in rows:
        item_id = str(row.get("item_id", "")).strip().lower()
        if not item_id:
            continue
        numeric_values = [
            number
            for key, value in row.items()
            if str(key).strip().lower() not in {"item", "item_id"}
            and (number := _number(value)) is not None
        ]
        if numeric_values:
            indexed[item_id] = numeric_values
    return indexed


def _number(value: Any) -> float | None:
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _first(values: list[float]) -> float | None:
    return values[0] if values else None


def _growth(values: list[float]) -> float | None:
    if len(values) < 2 or values[1] == 0:
        return None
    return round((values[0] / values[1] - 1) * 100, 4)


def _positive_mean(values: list[float]) -> float | None:
    positive = [value for value in values if value > 0]
    return mean(positive) if positive else None
