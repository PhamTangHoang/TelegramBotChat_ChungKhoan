from types import SimpleNamespace

from app.llm.schemas import PP10AIAction, PP10AICriterion, PP10AIReport
from app.services.analysis_service import MarketAnalysisService


class DirectGemini:
    model = "test-model"

    def generate_pp10_report(self, **kwargs: object) -> PP10AIReport:
        maximums = (10, 8, 8, 8, 8, 8, 7, 5, 6, 8, 4, 5, 5, 4, 4, 2)
        return PP10AIReport(
            total_score=64,
            grade="B",
            confidence="LOW",
            signal="TRUNG TÍNH",
            risk="TRUNG BÌNH",
            preliminary_conclusion="Đây là nhận định AI, chưa có dữ liệu live.",
            criteria=[
                PP10AICriterion(
                    criterion_id=index,
                    score=0,
                    status="AI_INFERENCE",
                    assessment="AI suy luận tham khảo.",
                    data_note="Không có dữ liệu live.",
                )
                for index, _ in enumerate(maximums, start=1)
            ],
            action_plan=[
                PP10AIAction(
                    scenario="Kịch bản 1 (Tích cực)",
                    price_zone="Chưa xác định",
                    strategy="Chờ xác nhận.",
                ),
                PP10AIAction(
                    scenario="Kịch bản 2 (Trung tính)",
                    price_zone="Chưa xác định",
                    strategy="Theo dõi.",
                ),
                PP10AIAction(
                    scenario="Kịch bản 3 (Tiêu cực)",
                    price_zone="Chưa xác định",
                    strategy="Không kết luận.",
                ),
            ],
            conclusion_action="CHỈ THAM KHẢO",
            conclusion_reason="Cần dữ liệu thực tế.",
            expectation="Chưa thể xác định.",
            key_note="Không có dữ liệu live.",
        )


def test_analyze_uses_gemini_directly_without_market_provider() -> None:
    gemini = DirectGemini()

    class FailingProvider:
        def get_ohlcv(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("AI-only analyze must not call the market provider")

    service = MarketAnalysisService(
        provider=FailingProvider(),
        session_factory=lambda: (_ for _ in ()).throw(
            AssertionError("AI-only analyze must not open a database session")
        ),
        calendar=object(),
        settings=SimpleNamespace(
            rule_version="1.5.0",
            volume_ratio_threshold=1.5,
            volume_min_elapsed_minutes=15,
            pp10_version="2.0.0",
        ),
        gemini=gemini,
    )

    import asyncio

    report = asyncio.run(service.analyze("fpt"))

    assert report.chart is None
    assert "BÁO CÁO PP10ULTI 2.0 – FPT" in report.text
    assert "AI" in report.text
    assert report.gemini_task is None
