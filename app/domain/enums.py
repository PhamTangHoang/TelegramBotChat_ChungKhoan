from enum import StrEnum


class PriceBasis(StrEnum):
    RAW_OHLCV = "RAW_OHLCV"
    ADJUSTED_CLOSE = "ADJUSTED_CLOSE"


class Signal(StrEnum):
    BULLISH = "BULLISH"
    NEUTRAL = "NEUTRAL"
    BEARISH = "BEARISH"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class Risk(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RuleStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_EVALUATED = "NOT_EVALUATED"


class EvaluationStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_EVALUATED = "NOT_EVALUATED"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


class DataFreshness(StrEnum):
    FRESH = "fresh"
    STALE_CACHE = "stale_cache"


class AnalysisKind(StrEnum):
    INTRADAY = "INTRADAY"
    FINAL = "FINAL"
