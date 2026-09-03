from collections.abc import Callable
import time
from typing import TypeVar


T = TypeVar("T")


class CircuitOpenError(RuntimeError):
    """Raised when a provider circuit is open and the call is rejected."""


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, reset_timeout_seconds: float = 60.0) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be positive")
        self.failure_threshold = failure_threshold
        self.reset_timeout_seconds = reset_timeout_seconds
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at >= self.reset_timeout_seconds:
            self._opened_at = None
            self._failures = 0
            return False
        return True

    def call(self, operation: Callable[[], T]) -> T:
        if self.is_open:
            raise CircuitOpenError("provider circuit is open")
        try:
            result = operation()
        except Exception:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._opened_at = time.monotonic()
            raise
        self._failures = 0
        self._opened_at = None
        return result


def retry_call(
    operation: Callable[[], T],
    *,
    attempts: int = 3,
    backoff_seconds: float = 0.5,
    retry_exceptions: tuple[type[BaseException], ...] = (TimeoutError, ConnectionError),
) -> T:
    if attempts < 1:
        raise ValueError("attempts must be positive")
    for attempt in range(attempts):
        try:
            return operation()
        except retry_exceptions:
            if attempt == attempts - 1:
                raise
            time.sleep(backoff_seconds * (2**attempt))
    raise AssertionError("retry loop did not return or raise")
