import logging
from collections.abc import Callable, Mapping
from datetime import date, datetime
from typing import Any

from app.data.errors import NoMarketDataError, ProviderSchemaError
from app.data.normalizer import normalize_index, normalize_ohlcv
from app.data.providers.base import MarketDataProvider
from app.data.providers.resilience import CircuitBreaker, retry_call

logger = logging.getLogger(__name__)


class VnstockProvider(MarketDataProvider):
    """Lazy vnstock adapter; importing vnstock is deferred until a live call."""

    def __init__(
        self,
        *,
        source: str = "kbs",
        client_factory: Callable[[], Any] | None = None,
        listing_factory: Callable[..., Any] | None = None,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        normalized_source = source.strip().lower()
        if normalized_source not in {"kbs", "vci"}:
            raise ValueError("vnstock source must be kbs or vci")
        self.source = normalized_source
        self._client_factory = client_factory or self._default_client
        self._listing_factory = listing_factory or self._default_listing
        self._breaker = breaker or CircuitBreaker()
        self._exchange_cache: dict[str, str] = {}
        self._listing_loaded = False

    @staticmethod
    def _default_client() -> Any:
        try:
            from vnstock import Market
        except ImportError as exc:
            raise ProviderSchemaError(
                "vnstock is not installed; install the pinned production dependency"
            ) from exc
        return Market()

    def _default_listing(self, **_: Any) -> Any:
        try:
            from vnstock import Listing
        except ImportError as exc:
            raise ProviderSchemaError(
                "vnstock Listing is not installed; install the pinned production dependency"
            ) from exc
        return Listing(source=self.source, show_log=False)

    def _fetch(self, operation: Callable[[], Any]) -> Any:
        return self._breaker.call(lambda: retry_call(operation))

    def get_ohlcv(
        self,
        symbol: str,
        start: date,
        end: date,
        *,
        exchange: str = "HOSE",
        is_final: bool = False,
    ):
        normalized_symbol = symbol.strip().upper()
        if self._listing_loaded and normalized_symbol not in self._exchange_cache:
            raise NoMarketDataError(f"No market data for {normalized_symbol}")

        def operation() -> Any:
            client = self._client_factory()
            return client.equity(symbol=symbol).ohlcv(
                start=start.isoformat(),
                end=end.isoformat(),
                interval="1D",
                count=400,
                source=self.source,
            )

        try:
            rows = self._fetch(operation)
        except Exception as exc:
            if _contains_no_data_error(exc):
                raise NoMarketDataError(f"No market data for {symbol}") from exc
            raise
        rows = _deduplicate_ohlcv_rows(rows)
        return normalize_ohlcv(
            rows,
            symbol=symbol,
            exchange=exchange,
            source="vnstock",
            is_final=is_final,
            volume_semantics="daily_total" if is_final else "regular_cumulative",
        )

    def resolve_exchange(self, symbol: str) -> str | None:
        normalized_symbol = symbol.strip().upper()
        if normalized_symbol in self._exchange_cache:
            return self._exchange_cache[normalized_symbol]
        if self._listing_loaded:
            return None
        try:
            listing = self._listing_factory(source=self.source, show_log=False)
            try:
                table = listing.symbols_by_exchange(get_all=True, show_log=False)
            except TypeError:
                table = listing.symbols_by_exchange(show_log=False)
            records = table.to_dict(orient="records") if hasattr(table, "to_dict") else table
            for row in records:
                if not isinstance(row, Mapping):
                    continue
                row_symbol = str(row.get("symbol", "")).strip().upper()
                exchange = str(row.get("exchange", "")).strip().upper()
                if row_symbol and exchange in {"HOSE", "HNX", "UPCOM"}:
                    self._exchange_cache[row_symbol] = exchange
        except Exception:
            logger.warning("vnstock exchange listing unavailable", exc_info=True)
            return None
        self._listing_loaded = True
        return self._exchange_cache.get(normalized_symbol)

    def get_market_index(
        self, index_code: str, start: date, end: date, *, is_final: bool = False
    ):
        def operation() -> Any:
            client = self._client_factory()
            return client.index(symbol=index_code).ohlcv(
                start=start.isoformat(),
                end=end.isoformat(),
                interval="1D",
                count=400,
                source=self.source,
            )

        rows = _deduplicate_index_rows(self._fetch(operation))
        return normalize_index(rows, index_code=index_code, source="vnstock", is_final=is_final)


def _deduplicate_index_rows(rows: Any) -> list[Any]:
    return _deduplicate_rows(rows, kind="index")


def _deduplicate_ohlcv_rows(rows: Any) -> list[Any]:
    return _deduplicate_rows(rows, kind="equity")


def _deduplicate_rows(rows: Any, *, kind: str) -> list[Any]:
    if hasattr(rows, "to_dict"):
        records = rows.to_dict(orient="records")
    elif isinstance(rows, Mapping):
        records = [rows]
    else:
        records = list(rows)

    deduplicated: dict[object, Any] = {}
    for row in records:
        if not isinstance(row, Mapping):
            return records
        key = _index_date_key(row)
        if key in deduplicated:
            logger.warning(
                "vnstock returned duplicate %s date=%s; keeping last row", kind, key
            )
        deduplicated[key] = row
    return list(deduplicated.values())


def _index_date_key(row: Mapping[str, Any]) -> object:
    for field in ("trading_date", "date", "time", "timestamp"):
        if field not in row:
            continue
        value = row[field]
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            raw = value.strip().replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(raw).date()
            except ValueError:
                return f"raw:{value}"
        return f"raw:{value!r}"
    return f"missing:{id(row)}"


def _contains_no_data_error(error: BaseException) -> bool:
    """Recognize vnstock's wrapped empty-result error without masking other failures."""
    pending: list[BaseException] = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        message = str(current).lower()
        if (
            "dữ liệu trống" in message
            or "no data" in message
            or "empty data" in message
            or "invalid symbol" in message
            or "format is not recognized" in message
        ):
            return True
        cause = current.__cause__ or current.__context__
        if cause is not None:
            pending.append(cause)
        last_attempt = getattr(current, "last_attempt", None)
        exception = getattr(last_attempt, "exception", None)
        if callable(exception):
            nested = exception()
            if nested is not None:
                pending.append(nested)
    return False
