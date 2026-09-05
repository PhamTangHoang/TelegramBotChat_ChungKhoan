from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.analysis.pp10 import PP10Evaluator
from app.chart.chart_engine import ChartAttachment
from app.domain.enums import AnalysisKind, DataFreshness, EvaluationStatus, Risk, RuleStatus, Signal
from app.domain.schemas import IndicatorSnapshot, RuleReason, RuleResult
from app.telegram.access_control import AccessDenied, RateLimiter, WhitelistAccessController
from app.telegram.commands import HELP_TEXT, command_menu
from app.telegram.formatter import (
    chunk_message,
    format_ai_pp10_report,
    format_news_report,
    format_technical_report,
)
from app.telegram.handlers import TelegramReport, _classify_text, _send_analysis_report


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
    assert "Giá tham chiếu: 110.000 VND/cổ phiếu" in report
    assert "Đơn vị giá: VND/cổ phiếu" in report


def test_report_formats_stock_price_indicators_as_vnd() -> None:
    indicators = IndicatorSnapshot(
        price=Decimal("22.25"),
        ma20=21.5,
        ma50=20.0,
        ma150=19.0,
        ma200=18.0,
        rsi14=60,
        macd_histogram=1,
        atr14=1.25,
        volume_ratio_projected=2,
        elapsed_trading_minutes=60,
        relative_return=0.05,
        as_of=datetime(2026, 9, 3, 3),
        is_final=False,
    )
    result = RuleResult(
        score=1,
        max_score=1,
        signal=Signal.BULLISH,
        confidence_raw=1,
        reasons=[],
        risk=Risk.LOW,
        risk_points=0,
        risk_reasons=[],
        rule_version="1.5.0",
    )

    report = format_technical_report(
        symbol="ACB",
        as_of=indicators.as_of,
        analysis_kind=AnalysisKind.INTRADAY,
        is_final=False,
        indicators=indicators,
        rule_result=result,
        data_freshness=DataFreshness.FRESH,
    )

    assert "Giá tham chiếu: 22.250 VND/cổ phiếu" in report
    assert "\nGiá tham chiếu: 22.25\n" not in report


def test_message_chunking_preserves_all_content_and_limit() -> None:
    text = "\n".join(f"line {i}" for i in range(100))
    chunks = chunk_message(text, max_length=100)

    assert all(len(chunk) <= 100 for chunk in chunks)
    assert "".join(chunks).replace("\n", "") == text.replace("\n", "")


def test_natural_text_classification_supports_analysis_chart_market_and_help() -> None:
    assert _classify_text("phân tích mã FPT") == ("analyze", "FPT")
    assert _classify_text("analyze FPT") == ("analyze", "FPT")
    assert _classify_text("phân tích cho t mã REE xem") == ("analyze", "REE")
    assert _classify_text("phân tích cổ phiếu ACB") == ("analyze", "ACB")
    assert _classify_text("tin tức FPT") == ("news", "FPT")
    assert _classify_text("tin tức về mã ACB") == ("news", "ACB")
    assert _classify_text("tin tức cổ phiếu REE") == ("news", "REE")
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


def test_news_report_does_not_render_html_from_existing_stored_summary() -> None:
    item = SimpleNamespace(
        source="Example Source",
        title="FPT headline",
        summary="<div>Revenue <a href='https://example.test'>grew</a></div>",
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

    assert "<div>" not in report
    assert "<a" not in report
    assert "Revenue grew" in report


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
                value={"price": 22.25, "ma20": 21.5, "ma50": 20.0},
                threshold="Price > MA20 > MA200",
                data_source="not_available",
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
    assert "Tổng điểm: 1/1 tiêu chí có dữ liệu" in report
    assert "CHƯA CÓ DỮ LIỆU" in report
    assert "Price > MA20 > MA200" in report
    assert (
        "Dữ liệu: price: 22.250 VND/cổ phiếu, ma20: 21.500 VND/cổ phiếu, "
        "ma50: 20.000 VND/cổ phiếu"
    ) in report
    assert "3. KẾ HOẠCH HÀNH ĐỘNG THAM KHẢO" in report
    assert "POSITION PLAN" not in report


def test_pp10_report_uses_structured_vietnamese_summary_and_action_plan() -> None:
    indicators = IndicatorSnapshot(
        price=Decimal("22.25"),
        elapsed_trading_minutes=60,
        as_of=datetime(2026, 9, 3, 3),
        is_final=False,
    )
    pp10 = PP10Evaluator(version="2.0.0").evaluate(indicators)
    rule_result = RuleResult(
        score=0,
        max_score=0,
        signal=Signal.INSUFFICIENT_DATA,
        confidence_raw=None,
        reasons=[],
        risk=Risk.LOW,
        risk_points=0,
        risk_reasons=[],
        rule_version="1.5.0",
    )

    report = format_technical_report(
        symbol="acb",
        as_of=indicators.as_of,
        analysis_kind=AnalysisKind.INTRADAY,
        is_final=False,
        indicators=indicators,
        rule_result=rule_result,
        data_freshness=DataFreshness.FRESH,
        pp10=pp10,
    )

    assert "BÁO CÁO PP10ULTI 2.0 – ACB" in report
    assert "1. TỔNG ĐIỂM PP10ULTI 2.0" in report
    assert "Độ phủ dữ liệu: 0/16 tiêu chí" in report
    assert "2. CHI TIẾT CÁC HẠNG MỤC" in report
    assert "NHÓM KỸ THUẬT" in report
    assert "NHÓM DÒNG TIỀN" in report
    assert "NHÓM ĐỘNG LƯỢNG" in report
    assert "NHÓM CƠ BẢN" in report
    assert "NHÓM ĐỊNH GIÁ & VĨ MÔ" in report
    assert "NHÓM QUẢN TRỊ VỊ THẾ" in report
    assert "3. KẾ HOẠCH HÀNH ĐỘNG" in report
    assert "Kịch bản 1 (Tích cực)" in report
    assert "🔔 KẾT LUẬN" in report
    assert "POSITION PLAN" not in report
    assert "GEMINI ANALYSIS" not in report


def test_ai_pp10_report_uses_sample_headings_without_market_data_or_chart() -> None:
    report = format_ai_pp10_report(
        symbol="fpt",
        as_of=datetime(2026, 9, 4, 9, 0),
        report=SimpleNamespace(
            total_score=64,
            grade="B",
            confidence="LOW",
            signal="TRUNG TÍNH",
            risk="TRUNG BÌNH",
            preliminary_conclusion="Đây là nhận định AI.",
            criteria=[
                SimpleNamespace(
                    criterion_id=index,
                    score=0,
                    status="AI_INFERENCE",
                    assessment="AI suy luận tham khảo.",
                    data_note="Không có dữ liệu live.",
                )
                for index in range(1, 17)
            ],
            action_plan=[
                SimpleNamespace(
                    scenario=f"Kịch bản {index}",
                    price_zone="Chưa xác định",
                    strategy="Theo dõi.",
                )
                for index in range(1, 4)
            ],
            conclusion_action="CHỈ THAM KHẢO",
            conclusion_reason="Cần dữ liệu thực tế.",
            expectation="Chưa xác định.",
            key_note="Không có dữ liệu live.",
        ),
    )

    assert "BÁO CÁO PP10ULTI 2.0 – FPT" in report
    assert "Tổng điểm AI tham khảo: 64/100" in report
    assert "NHÓM KỸ THUẬT" in report
    assert "🤖 AI SUY LUẬN" in report
    assert "3. KẾ HOẠCH HÀNH ĐỘNG THAM KHẢO" in report
    assert "không có OHLCV live" in report
    assert "[ Photo ]" not in report


def test_analysis_sender_delivers_gemini_follow_up_after_technical_report() -> None:
    messages: list[str] = []

    class Message:
        async def answer(self, text: str) -> None:
            messages.append(text)

    async def follow_up() -> str:
        return "GIẢI THÍCH GEMINI\n• Kết luận: Tiếp tục theo dõi."

    async def scenario() -> None:
        await _send_analysis_report(
            Message(),
            TelegramReport(
                text="Báo cáo PP10 kỹ thuật",
                gemini_task=follow_up(),
            ),
        )

    import asyncio

    asyncio.run(scenario())

    assert messages == [
        "Báo cáo PP10 kỹ thuật",
        "GIẢI THÍCH GEMINI\n• Kết luận: Tiếp tục theo dõi.",
    ]


def test_analysis_sender_delivers_chart_bundle_before_report() -> None:
    import importlib.util

    if importlib.util.find_spec("aiogram") is None:
        pytest.skip("aiogram is installed in the Docker image")
    events: list[object] = []

    class Message:
        async def answer(self, text: str) -> None:
            events.append(text)

        async def answer_photo(self, photo: object, **kwargs: object) -> None:
            events.append((photo, kwargs))

    async def scenario() -> None:
        await _send_analysis_report(
            Message(),
            TelegramReport(
                text="Báo cáo PP10",
                charts=(
                    ChartAttachment(
                        filename="HDB-daily-trend.png",
                        caption="Xu hướng ngày",
                        content=b"fake-png",
                    ),
                ),
            ),
        )

    import asyncio

    asyncio.run(scenario())

    assert len(events) == 2
    assert isinstance(events[0], tuple)
    assert events[1] == "Báo cáo PP10"
