from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from app.data.errors import InvalidMarketDataError, ProviderSchemaError, ProviderSemanticError
from app.domain.schemas import IndexCandle, MarketCandle


REQUIRED_OHLCV = ("open", "high", "low", "close", "volume")
DATE_ALIASES = ("trading_date", "date", "time", "timestamp")


def _records(rows: Any) -> list[Mapping[str, Any]]:
    if hasattr(rows, "to_dict"):
        rows = rows.to_dict(orient="records")
    if isinstance(rows, Mapping):
        rows = [rows]
    if not isinstance(rows, Iterable) or isinstance(rows, (str, bytes)):
        raise ProviderSchemaError("provider response must be an iterable of row mappings")
    result = list(rows)
    if not all(isinstance(row, Mapping) for row in result):
        raise ProviderSchemaError("every provider row must be a mapping")
    return result


def _normalized_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key).strip().lower(): value for key, value in row.items()}


def _date_value(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        raw = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(raw).date()
        except ValueError:
            try:
                return date.fromisoformat(raw)
            except ValueError as exc:
                raise ProviderSchemaError(f"invalid trading date: {value!r}") from exc
    raise ProviderSchemaError(f"unsupported trading date value: {value!r}")


def _datetime_value(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise ProviderSchemaError(f"invalid provider timestamp: {value!r}") from exc
    raise ProviderSchemaError(f"unsupported provider timestamp value: {value!r}")


def _decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ProviderSchemaError(f"invalid numeric value for {field}: {value!r}") from exc
    if not result.is_finite():
        raise ProviderSchemaError(f"non-finite numeric value for {field}")
    return result


def _find_date(row: Mapping[str, Any]) -> Any:
    for alias in DATE_ALIASES:
        if alias in row:
            return row[alias]
    raise ProviderSchemaError(f"missing date column; expected one of {DATE_ALIASES}")


def normalize_ohlcv(
    rows: Any,
    *,
    symbol: str,
    exchange: str,
    source: str,
    is_final: bool = False,
    volume_semantics: str = "regular_cumulative",
) -> list[MarketCandle]:
    if volume_semantics not in {"regular_cumulative", "daily_total"}:
        raise ProviderSemanticError(
            "volume semantics must be explicitly regular_cumulative or daily_total"
        )

    normalized_rows = [_normalized_row(row) for row in _records(rows)]
    if not normalized_rows:
        raise ProviderSchemaError("provider OHLCV response is empty")
    result: list[MarketCandle] = []
    seen_dates: set[date] = set()
    for row in normalized_rows:
        missing = [field for field in REQUIRED_OHLCV if field not in row]
        if missing:
            raise ProviderSchemaError(f"missing OHLCV columns: {', '.join(missing)}")
        trading_date = _date_value(_find_date(row))
        if trading_date in seen_dates:
            raise ProviderSchemaError(f"duplicate trading date: {trading_date.isoformat()}")
        seen_dates.add(trading_date)
        values = {
            "symbol": symbol,
            "exchange": exchange,
            "trading_date": trading_date,
            "open": _decimal(row["open"], "open"),
            "high": _decimal(row["high"], "high"),
            "low": _decimal(row["low"], "low"),
            "close": _decimal(row["close"], "close"),
            "volume": _decimal(row["volume"], "volume"),
            "adjusted_close": (
                _decimal(row["adjusted_close"], "adjusted_close")
                if row.get("adjusted_close") is not None
                else None
            ),
            "source": source,
            "provider_timestamp": _datetime_value(row.get("provider_timestamp")),
            "is_final": is_final,
        }
        try:
            result.append(MarketCandle.model_validate(values))
        except ValidationError as exc:
            raise InvalidMarketDataError(str(exc)) from exc
    return sorted(result, key=lambda item: item.trading_date)


def normalize_index(rows: Any, *, index_code: str, source: str, is_final: bool = False) -> list[IndexCandle]:
    normalized_rows = [_normalized_row(row) for row in _records(rows)]
    if not normalized_rows:
        raise ProviderSchemaError("provider index response is empty")
    result: list[IndexCandle] = []
    seen_dates: set[date] = set()
    for row in normalized_rows:
        missing = [field for field in REQUIRED_OHLCV if field not in row]
        if missing:
            raise ProviderSchemaError(f"missing index OHLC columns: {', '.join(missing)}")
        trading_date = _date_value(_find_date(row))
        if trading_date in seen_dates:
            raise ProviderSchemaError(f"duplicate index date: {trading_date.isoformat()}")
        seen_dates.add(trading_date)
        values = {
            "index_code": index_code,
            "trading_date": trading_date,
            "open": _decimal(row["open"], "open"),
            "high": _decimal(row["high"], "high"),
            "low": _decimal(row["low"], "low"),
            "close": _decimal(row["close"], "close"),
            "source": source,
            "provider_timestamp": _datetime_value(row.get("provider_timestamp")),
            "is_final": is_final,
        }
        try:
            result.append(IndexCandle.model_validate(values))
        except ValidationError as exc:
            raise InvalidMarketDataError(str(exc)) from exc
    return sorted(result, key=lambda item: item.trading_date)
