from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.domain.enums import Signal
from app.llm.gemini import GeminiError, GeminiExplainer, explanation_conflicts_with_signal
from app.llm.schemas import GeminiExplanation, PP10AIAction, PP10AICriterion, PP10AIReport


def explanation(**overrides: str) -> GeminiExplanation:
    values = {
        "market_summary": "Market is mixed.",
        "technical_explanation": "Price and moving averages are supplied by the rule engine.",
        "news_context": "No event context was supplied.",
        "bull_case": "Trend remains constructive.",
        "bear_case": "A reversal remains possible.",
        "risk": "Monitor volatility.",
        "conclusion": "Primary signal is BULLISH.",
    }
    values.update(overrides)
    return GeminiExplanation.model_validate(values)


class FakeModels:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def generate_content(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.response


class SequenceModels:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def generate_content(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.responses.pop(0)


def test_gemini_uses_structured_schema_and_validates_response() -> None:
    models = FakeModels(SimpleNamespace(parsed=explanation().model_dump()))
    explainer = GeminiExplainer(
        api_key="test", model="test-model", client=SimpleNamespace(models=models)
    )

    result = explainer.explain(
        quantitative_context={"rsi14": 60},
        event_context=[],
        decision_context={"signal": "BULLISH", "score": 5},
    )

    assert result.conclusion == "Primary signal is BULLISH."
    config = models.calls[0]["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_schema["title"] == "GeminiExplanation"
    assert "additionalProperties" not in config.response_schema


def _ai_report() -> PP10AIReport:
    maximums = (10, 8, 8, 8, 8, 8, 7, 5, 6, 8, 4, 5, 5, 4, 4, 2)
    return PP10AIReport(
        total_score=64,
        grade="B",
        confidence="LOW",
        signal="TRUNG TÍNH",
        risk="TRUNG BÌNH",
        preliminary_conclusion="Đây là nhận định AI, chưa có dữ liệu live để xác nhận.",
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
                price_zone="Chưa xác định khi thiếu giá live",
                strategy="Chờ người dùng cung cấp dữ liệu để xác nhận.",
            ),
            PP10AIAction(
                scenario="Kịch bản 2 (Trung tính)",
                price_zone="Chưa xác định khi thiếu giá live",
                strategy="Theo dõi thêm dữ liệu.",
            ),
            PP10AIAction(
                scenario="Kịch bản 3 (Tiêu cực)",
                price_zone="Chưa xác định khi thiếu giá live",
                strategy="Không kết luận định lượng.",
            ),
        ],
        conclusion_action="CHỈ THAM KHẢO",
        conclusion_reason="Cần dữ liệu thực tế để xác nhận.",
        expectation="Chưa thể xác định mục tiêu giá.",
        key_note="Không có dữ liệu thị trường live được truyền vào.",
    )


def test_gemini_builds_structured_ai_only_pp10_report() -> None:
    models = FakeModels(SimpleNamespace(parsed=_ai_report().model_dump()))
    explainer = GeminiExplainer(
        api_key="test", model="test-model", client=SimpleNamespace(models=models)
    )

    result = explainer.generate_pp10_report(
        symbol="FPT",
        analysis_date="2026-09-04",
        quantitative_context={
            "latest_candle": {"close": "27.200", "volume": 1000000},
            "ohlcv_daily": [{"trading_date": "2026-09-04", "close": "27.200"}],
        },
    )

    assert result.total_score == 64
    config = models.calls[0]["config"]
    assert config.response_schema["title"] == "PP10AIReport"
    assert config.max_output_tokens == 6000
    prompt = models.calls[0]["contents"]
    assert "OHLCV" in prompt
    assert "ohlcv_daily" in prompt
    assert "FPT" in prompt


def test_gemini_pp10_receives_chart_images_as_model_parts() -> None:
    models = FakeModels(SimpleNamespace(parsed=_ai_report().model_dump()))
    explainer = GeminiExplainer(
        api_key="test", model="test-model", client=SimpleNamespace(models=models)
    )

    explainer.generate_pp10_report(
        symbol="HDB",
        analysis_date="2026-09-04",
        quantitative_context={},
        chart_images=[b"fake-png"],
    )

    contents = models.calls[0]["contents"]
    assert isinstance(contents, list)
    assert len(contents) == 2
    assert getattr(contents[1], "inline_data", None) is not None


def test_gemini_can_judge_openrouter_analyst_drafts() -> None:
    models = FakeModels(SimpleNamespace(parsed=_ai_report().model_dump()))
    explainer = GeminiExplainer(
        api_key="test", model="test-model", client=SimpleNamespace(models=models)
    )

    result = explainer.generate_pp10_report(
        symbol="FPT",
        analysis_date="2026-09-04",
        quantitative_context={"latest_candle": {"close": "27.200"}},
        debate_drafts=[
            {
                "role": "Chuyên gia kỹ thuật",
                "model": "technical-model",
                "content": "Quan điểm kỹ thuật tham khảo.",
            }
        ],
    )

    assert result.total_score == 64
    prompt = models.calls[0]["contents"]
    assert "Debate Drafts" in prompt
    assert "technical-model" in prompt


def test_gemini_repairs_pp10_report_when_a_score_exceeds_criterion_limit() -> None:
    invalid = _ai_report().model_dump()
    invalid["criteria"][14]["score"] = 5
    models = SequenceModels(
        [
            SimpleNamespace(parsed=invalid),
            SimpleNamespace(parsed=_ai_report().model_dump()),
        ]
    )
    explainer = GeminiExplainer(
        api_key="test", model="test-model", client=SimpleNamespace(models=models)
    )

    result = explainer.generate_pp10_report(
        symbol="HDB", analysis_date="2026-09-04", quantitative_context={}
    )

    assert result.criteria[14].score == 0
    assert len(models.calls) == 2
    repair_prompt = models.calls[1]["contents"]
    assert "TOÀN BỘ JSON" in repair_prompt
    assert "criterion 15" in repair_prompt


def test_invalid_gemini_response_is_recoverable() -> None:
    models = FakeModels(SimpleNamespace(text='{"conclusion":"only one field"}'))
    explainer = GeminiExplainer(
        api_key="test", model="test-model", client=SimpleNamespace(models=models)
    )

    with pytest.raises(GeminiError):
        explainer.explain(quantitative_context={}, event_context=[], decision_context={})


def test_gemini_accepts_json_wrapped_in_markdown_fence() -> None:
    payload = explanation().model_dump_json()
    models = FakeModels(SimpleNamespace(text=f"```json\n{payload}\n```"))
    explainer = GeminiExplainer(
        api_key="test", model="test-model", client=SimpleNamespace(models=models)
    )

    result = explainer.explain(quantitative_context={}, event_context=[], decision_context={})

    assert result.conclusion == "Primary signal is BULLISH."


def test_gemini_chat_returns_plain_text() -> None:
    models = FakeModels(SimpleNamespace(text="Xin chào! Dùng /pt FPT để phân tích."))
    explainer = GeminiExplainer(
        api_key="test", model="test-model", client=SimpleNamespace(models=models)
    )

    assert explainer.chat("xin chào") == "Xin chào! Dùng /pt FPT để phân tích."


def test_gemini_client_uses_a_bounded_http_timeout() -> None:
    fake_client = object()
    with patch("google.genai.Client", return_value=fake_client) as client_factory:
        explainer = GeminiExplainer(
            api_key="test", model="test-model", timeout_seconds=8
        )

        assert explainer.client is fake_client

    http_options = client_factory.call_args.kwargs["http_options"]
    assert http_options.timeout == 10000


def test_conflict_flag_does_not_change_primary_signal() -> None:
    assert explanation_conflicts_with_signal(
        explanation(conclusion="Primary signal is BEARISH."), Signal.BULLISH
    )
    assert not explanation_conflicts_with_signal(explanation(), Signal.BULLISH)
