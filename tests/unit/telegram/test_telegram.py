from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.domain.enums import AnalysisKind, DataFreshness, EvaluationStatus, Risk, RuleStatus, Signal
from app.domain.schemas import IndicatorSnapshot, RuleReason, RuleResult
from app.telegram.access_control import AccessDenied, RateLimiter, WhitelistAccessController
from app.telegram.commands import HELP_TEXT, command_menu
from app.telegram.formatter import chunk_message, format_news_report, format_technical_report
from app.telegram.handlers import _classify_text


def test_whitelist_and_rate_limit_are_independent() -> None:
    WhitelistAccessController([123]).check(123)
    with pytest.raises(AccessDenied):
        WhitelistAccessController([123]).check(456)
    WhitelistAccessController([], public_access=True).check(456)

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


def test_natural_text_classification_supports_analysis_chart_market_and_help() -> None:
    assert _classify_text("phân tích mã FPT") == ("analyze", "FPT")
    assert _classify_text("analyze FPT") == ("analyze", "FPT")
    assert _classify_text("tin tức FPT") == ("news", "FPT")
    assert _classify_text("tin thị trường") == ("news", None)
    assert _classify_text("vẽ biểu đồ VNM") == ("chart", "VNM")
    assert _classify_text("thị trường hôm nay thế nào") == ("market", None)
    assert _classify_text("xin chào") == ("help", None)


def test_telegram_command_menu_and_help_describe_the_public_commands() -> None:
    commands = {command.command: command.description for command in command_menu()}

    assert set(commands) == {"start", "help", "analyze", "chart", "news", "market"}
    assert "PP10Ulti" in HELP_TEXT
    assert "/news FPT" in HELP_TEXT


def test_news_report_shows_source_times_summary_and_original_link() -> None:
    item = SimpleNamespace(
        source="Example Source",
        title="FPT công bố kết quả kinh doanh",
        summary="Doanh thu tăng trưởng.",
        url="https://example.test/fpt-result",
        published_at=datetime(2026, 9, 3, 3, 0),
        fetched_at=datetime(2026, 9, 3, 4, 0),
    )

    report = format_news_report(
        symbol="FPT",
        as_of=datetime(2026, 9, 3, 4, 0),
        items=[item],
        status="AVAILABLE",
    )

    assert "FPT — News" in report
    assert "FPT công bố kết quả kinh doanh" in report
    assert "Example Source" in report
    assert "Doanh thu tăng trưởng." in report
    assert "https://example.test/fpt-result" in report
    assert "chưa được bot xác minh độc lập" in report


def test_unified_analysis_report_includes_pp10_score_and_data_gaps() -> None:
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
    rule_result = RuleResult(
        score=1,
        max_score=1,
        signal=Signal.NEUTRAL,
        confidence_raw=1,
        reasons=[],
        risk=Risk.LOW,
        risk_points=0,
        risk_reasons=[],
        rule_version="1.5.0",
    )
    pp10 = SimpleNamespace(
        score=1,
        max_score=1,
        evaluated_count=1,
        grade="C",
        confidence="Low",
        criteria=[
            SimpleNamespace(
                criterion_id="1",
                name="Xu hướng MA tổng thể",
                status=EvaluationStatus.DATA_UNAVAILABLE,
                reason="Thiếu MA200",
            )
        ],
        risk_plan=SimpleNamespace(
            entry_zone="N/A",
            add_zone="N/A",
            stop_loss="N/A",
            target="N/A",
            risk_reward="N/A",
        ),
    )

    report = format_technical_report(
        symbol="FPT",
        as_of=indicators.as_of,
        analysis_kind=AnalysisKind.INTRADAY,
        is_final=False,
        indicators=indicators,
        rule_result=rule_result,
        data_freshness=DataFreshness.FRESH,
        pp10=pp10,
    )

    assert "PP10ULTI" in report
    assert "Score: 1/1" in report
    assert "DATA_UNAVAILABLE" in report
    assert "POSITION PLAN" in report
