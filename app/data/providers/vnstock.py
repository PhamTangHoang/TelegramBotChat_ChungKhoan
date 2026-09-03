from datetime import date
from typing import Any, Callable

from app.data.errors import ProviderSchemaError
from app.data.normalizer import normalize_index, normalize_ohlcv
from app.data.providers.base import MarketDataProvider
from app.data.providers.resilience import CircuitBreaker, retry_call


class VnstockProvider(MarketDataProvider):
    """Lazy vnstock adapter; importing vnstock is deferred until a live call."""

    def __init__(
        self,
        *,
        source: str = "auto",
        client_factory: Callable[[], Any] | None = None,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self.source = source
        self._client_factory = client_factory or self._default_client
        self._breaker = breaker or CircuitBreaker()

    @staticmethod
    def _default_client() -> Any:
        try:
            from vnstock import Market
        except ImportError as exc:
            raise ProviderSchemaError(
                "vnstock is not installed; install the pinned production dependency"
            ) from exc
        return Market()

    def _fetch(self, operation: Callable[[], Any]) -> Any:
        return self._breaker.call(lambda: retry_call(operation))

    def get_ohlcv(
        self, symbol: str, start: date, end: date, *, is_final: bool = False
    ):
        def operation() -> Any:
            client = self._client_factory()
            return client.equity.ohlcv(
                symbol=symbol,
                start=start.isoformat(),
                end=end.isoformat(),
                interval="1D",
            )

        rows = self._fetch(operation)
        return normalize_ohlcv(
            rows,
            symbol=symbol,
            exchange="HOSE",
            source="vnstock",
            is_final=is_final,
            volume_semantics="daily_total" if is_final else "regular_cumulative",
        )

    def get_market_index(
        self, index_code: str, start: date, end: date, *, is_final: bool = False
    ):
        def operation() -> Any:
            client = self._client_factory()
            index_api = client.index
            if callable(index_api):
                index_api = index_api(index_code)
            return index_api.ohlcv(
                symbol=index_code,
                start=start.isoformat(),
                end=end.isoformat(),
                interval="1D",
            )

        rows = self._fetch(operation)
        return normalize_index(rows, index_code=index_code, source="vnstock", is_final=is_final)
