from datetime import datetime
from decimal import Decimal

import pytest

from app.domain.enums import AnalysisKind, DataFreshness, Risk, RuleStatus, Signal
from app.domain.schemas import IndicatorSnapshot, RuleReason, RuleResult
from app.telegram.access_control import AccessDenied, RateLimiter, WhitelistAccessController
from app.telegram.formatter import chunk_message, format_technical_report


def test_whitelist_and_rate_limit_are_independent() -> None:
    WhitelistAccessController([123]).check(123)
    with pytest.raises(AccessDenied):
        WhitelistAccessController([123]).check(456)

    now = [0.0]
    limiter = RateLimiter(2, clock=lambda: now[0])
    assert limiter.allow(123)
    assert limiter.allow(123)
    assert not limiter.allow(123)
    now[0] = 60.0
    assert limiter.allow(123)


def test_report_contains_disclaimer_and_does_not_show_confidence_percentage() -> None:
    indicators = IndicatorSnapshot(
        price=Decimal("110"),
        ma20=100,
        ma50=90,
        rsi14=60,
        macd_histogram=1,
        atr14=2,
        volume_ratio_projected=2,
        elapsed_trading_minutes=60,
        relative_return=0.05,
        as_of=datetime(2026, 9, 3, 3),
        is_final=False,
    )
    result = RuleResult(
        score=7,
        max_score=7,
        signal=Signal.BULLISH,
        confidence_raw=1,
        reasons=[
            RuleReason(
                rule_id=f"R{i}",
                message=f"Rule {i}",
                status=RuleStatus.PASS,
                value=1,
                threshold="> 0",
            )
            for i in range(1, 8)
        ],
        risk=Risk.LOW,
        risk_points=0,
        risk_reasons=[],
        rule_version="1.5.0",
    )

    report = format_technical_report(
        symbol="FPT",
        as_of=indicators.as_of,
        analysis_kind=AnalysisKind.INTRADAY,
        is_final=False,
        indicators=indicators,
        rule_result=result,
        data_freshness=DataFreshness.FRESH,
    )

    assert "không phải khuyến nghị đầu tư" in report
    assert "confidence_raw" not in report
    assert "100%" not in report


def test_message_chunking_preserves_all_content_and_limit() -> None:
    text = "\n".join(f"line {i}" for i in range(100))
    chunks = chunk_message(text, max_length=100)

    assert all(len(chunk) <= 100 for chunk in chunks)
    assert "".join(chunks).replace("\n", "") == text.replace("\n", "")
