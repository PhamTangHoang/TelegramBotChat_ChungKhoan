import json
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, get_args

import httpx
import pytest

from app.llm.openrouter import (
    HybridReportGenerator,
    OpenRouterClient,
    OpenRouterDebateExplainer,
    OpenRouterError,
)
from app.llm.schemas import PP10AIReport


def _report_payload() -> dict[str, Any]:
    neutral_signal = get_args(PP10AIReport.model_fields["signal"].annotation)[1]
    return {
        "total_score": 64,
        "grade": "B",
        "confidence": "LOW",
        "signal": neutral_signal,
        "risk": "TRUNG BÃŒNH",
        "preliminary_conclusion": "ÄÃ¢y lÃ  nháº­n Ä‘á»‹nh AI tham kháº£o.",
        "criteria": [
            {
                "criterion_id": index,
                "score": 0,
                "status": "AI_INFERENCE",
                "assessment": "AI suy luáº­n tham kháº£o.",
                "data_note": "Cáº§n kiá»ƒm chá»©ng thÃªm.",
            }
            for index in range(1, 17)
        ],
        "action_plan": [
            {
                "scenario": "Ká»‹ch báº£n 1",
                "price_zone": "ChÆ°a xÃ¡c Ä‘á»‹nh",
                "strategy": "Theo dÃµi thÃªm.",
            },
            {
                "scenario": "Ká»‹ch báº£n 2",
                "price_zone": "ChÆ°a xÃ¡c Ä‘á»‹nh",
                "strategy": "Theo dÃµi thÃªm.",
            },
            {
                "scenario": "Ká»‹ch báº£n 3",
                "price_zone": "ChÆ°a xÃ¡c Ä‘á»‹nh",
                "strategy": "KhÃ´ng káº¿t luáº­n Ä‘á»‹nh lÆ°á»£ng.",
            },
        ],
        "conclusion_action": "CHá»ˆ THAM KHáº¢O",
        "conclusion_reason": "Cáº§n dá»¯ liá»‡u thá»±c táº¿ Ä‘á»ƒ xÃ¡c nháº­n.",
        "expectation": "ChÆ°a thá»ƒ xÃ¡c Ä‘á»‹nh.",
        "key_note": "BÃ¡o cÃ¡o do AI táº¡o.",
    }


class FakeRequester:
    def __init__(self, response_for: Callable[[str, dict[str, Any]], str]) -> None:
        self.response_for = response_for
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        *,
        url: str,
        headers: dict[str, str],
        json: dict[str, Any],
    ) -> httpx.Response:
        self.calls.append({"url": url, "headers": headers, "json": json})
        model = str(json.get("model") or json["models"][0])
        content = self.response_for(model, json)
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            json={"model": model, "choices": [{"message": {"content": content}}]},
            request=request,
        )


def test_openrouter_client_uses_bearer_auth_and_returns_content() -> None:
    requester = FakeRequester(lambda _model, _body: "Xin chÃ o")
    client = OpenRouterClient(
        api_key="test-key",
        base_url="https://openrouter.ai/api/v1/",
        requester=requester,
    )

    result = client.complete(model="test-model", messages=[{"role": "user", "content": "hi"}])

    assert result.content == "Xin chÃ o"
    assert requester.calls[0]["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert requester.calls[0]["headers"]["Authorization"] == "Bearer test-key"


def test_debate_runs_analysts_and_judge_then_validates_pp10_report() -> None:
    payload = json.dumps(_report_payload(), ensure_ascii=False)

    def response_for(model: str, _body: dict[str, Any]) -> str:
        return payload if model == "judge-model" else f"Ý kiến độc lập từ {model}."

    requester = FakeRequester(response_for)
    explainer = OpenRouterDebateExplainer(
        api_key="test-key",
        analyst_models=("technical-model", "pattern-model", "risk-model"),
        judge_model="judge-model",
        client=OpenRouterClient(api_key="test-key", requester=requester),
    )

    result = explainer.generate_pp10_report(
        symbol="FPT",
        analysis_date="2026-09-04",
        quantitative_context={"latest_candle": {"close": 100}},
    )

    assert isinstance(result, PP10AIReport)
    assert result.total_score == 64
    assert len(requester.calls) == 4
    judge_call = next(
        call for call in requester.calls if call["json"].get("model") == "judge-model"
    )
    judge_prompt = judge_call["json"]["messages"][0]["content"]
    assert "technical-model" in judge_prompt
    assert "pattern-model" in judge_prompt
    assert judge_call["json"]["response_format"]["type"] == "json_schema"


def test_debate_keeps_working_when_one_analyst_fails() -> None:
    payload = json.dumps(_report_payload(), ensure_ascii=False)

    def response_for(model: str, _body: dict[str, Any]) -> str:
        if model == "pattern-model":
            raise httpx.TimeoutException("timed out")
        return payload if model == "judge-model" else f"Ý kiến từ {model}."

    requester = FakeRequester(response_for)
    explainer = OpenRouterDebateExplainer(
        api_key="test-key",
        analyst_models=("technical-model", "pattern-model", "risk-model"),
        judge_model="judge-model",
        client=OpenRouterClient(api_key="test-key", requester=requester),
    )

    result = explainer.generate_pp10_report(
        symbol="FPT", analysis_date="2026-09-04", quantitative_context={}
    )

    assert result.grade == "B"


def test_debate_fails_clearly_when_all_analysts_fail() -> None:
    requester = FakeRequester(lambda _model, _body: (_ for _ in ()).throw(httpx.TimeoutException()))
    explainer = OpenRouterDebateExplainer(
        api_key="test-key",
        analyst_models=("technical-model", "pattern-model"),
        judge_model="judge-model",
        client=OpenRouterClient(api_key="test-key", requester=requester),
    )

    with pytest.raises(OpenRouterError, match="No OpenRouter analyst response"):
        explainer.generate_pp10_report(
            symbol="FPT", analysis_date="2026-09-04", quantitative_context={}
        )


def test_hybrid_report_generator_falls_back_to_gemini() -> None:
    fallback_report = SimpleNamespace(total_score=42)

    class FailingGenerator:
        def generate_pp10_report(self, **_kwargs: Any) -> PP10AIReport:
            raise OpenRouterError("provider unavailable")

    class FallbackGenerator:
        def generate_pp10_report(self, **_kwargs: Any) -> Any:
            return fallback_report

    generator = HybridReportGenerator(primary=FailingGenerator(), fallback=FallbackGenerator())

    assert (
        generator.generate_pp10_report(symbol="FPT", analysis_date="2026-09-04")
        is fallback_report
    )
