import asyncio
import threading
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from app.analysis.pp10 import PP10Evaluator
from app.domain.enums import Risk, Signal
from app.domain.schemas import IndicatorSnapshot, RuleResult
from app.llm.schemas import GeminiExplanation
from app.services.analysis_service import AnalysisOutput, MarketAnalysisService


class SlowGemini:
    model = "test-model"

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def explain(self, **kwargs: object) -> GeminiExplanation:
        self.started.set()
        assert self.release.wait(timeout=2)
        return GeminiExplanation(
            market_summary="Tóm tắt thị trường.",
            technical_explanation="Phân tích kỹ thuật.",
            news_context="Không có tin được truyền vào.",
            bull_case="Kịch bản tích cực.",
            bear_case="Kịch bản tiêu cực.",
            risk="Rủi ro trung bình.",
            conclusion="Tiếp tục theo dõi.",
        )


def test_analyze_returns_technical_report_before_gemini_finishes() -> None:
    gemini = SlowGemini()
    service = MarketAnalysisService(
        provider=object(),
        session_factory=lambda: None,
        calendar=object(),
        settings=SimpleNamespace(
            rule_version="1.5.0",
            volume_ratio_threshold=1.5,
            volume_min_elapsed_minutes=15,
            pp10_version="2.0.0",
        ),
        gemini=gemini,
    )
    indicators = IndicatorSnapshot(
        price=Decimal("100"),
        elapsed_trading_minutes=60,
        as_of=datetime(2026, 9, 3, 3),
        is_final=False,
    )
    output = AnalysisOutput(
        symbol="FPT",
        text="Báo cáo PP10 kỹ thuật",
        chart=None,
        indicators=indicators,
        rule_result=RuleResult(
            score=0,
            max_score=0,
            signal=Signal.INSUFFICIENT_DATA,
            confidence_raw=None,
            reasons=[],
            risk=Risk.LOW,
            risk_points=0,
            risk_reasons=[],
            rule_version="1.5.0",
        ),
        pp10_result=PP10Evaluator().evaluate(indicators),
        analysis_run_id=None,
    )
    service.run_sync = lambda symbol, **kwargs: output  # type: ignore[method-assign]

    async def scenario() -> None:
        report = await service.analyze("FPT")

        assert report.text == "Báo cáo PP10 kỹ thuật"
        assert report.gemini_task is not None
        assert await asyncio.to_thread(gemini.started.wait, 1)

        gemini.release.set()
        follow_up = await report.gemini_task
        assert follow_up is not None
        assert "GIẢI THÍCH GEMINI" in follow_up

    asyncio.run(scenario())
