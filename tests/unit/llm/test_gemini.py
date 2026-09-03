from types import SimpleNamespace

import pytest

from app.domain.enums import Signal
from app.llm.gemini import GeminiError, GeminiExplainer, explanation_conflicts_with_signal
from app.llm.schemas import GeminiExplanation


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


def test_invalid_gemini_response_is_recoverable() -> None:
    models = FakeModels(SimpleNamespace(text='{"conclusion":"only one field"}'))
    explainer = GeminiExplainer(
        api_key="test", model="test-model", client=SimpleNamespace(models=models)
    )

    with pytest.raises(GeminiError):
        explainer.explain(quantitative_context={}, event_context=[], decision_context={})


def test_gemini_chat_returns_plain_text() -> None:
    models = FakeModels(SimpleNamespace(text="Xin chào! Dùng /pt FPT để phân tích."))
    explainer = GeminiExplainer(
        api_key="test", model="test-model", client=SimpleNamespace(models=models)
    )

    assert explainer.chat("xin chào") == "Xin chào! Dùng /pt FPT để phân tích."


def test_conflict_flag_does_not_change_primary_signal() -> None:
    assert explanation_conflicts_with_signal(
        explanation(conclusion="Primary signal is BEARISH."), Signal.BULLISH
    )
    assert not explanation_conflicts_with_signal(explanation(), Signal.BULLISH)
