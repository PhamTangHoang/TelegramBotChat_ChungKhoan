import pytest

from app.data.providers.resilience import CircuitBreaker, CircuitOpenError, retry_call


def test_circuit_breaker_opens_after_consecutive_failures() -> None:
    breaker = CircuitBreaker(failure_threshold=2)

    with pytest.raises(RuntimeError):
        breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("first")))
    with pytest.raises(RuntimeError):
        breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("second")))
    with pytest.raises(CircuitOpenError):
        breaker.call(lambda: "must not run")


def test_retry_call_retries_only_configured_attempts() -> None:
    attempts = 0

    def fail() -> None:
        nonlocal attempts
        attempts += 1
        raise TimeoutError("temporary")

    with pytest.raises(TimeoutError):
        retry_call(fail, attempts=3, backoff_seconds=0)

    assert attempts == 3
