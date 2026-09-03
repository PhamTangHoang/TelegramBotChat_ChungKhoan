from __future__ import annotations

import logging
from typing import Any

from app.domain.enums import Signal
from app.llm.prompts import build_prompt
from app.llm.schemas import GeminiExplanation

logger = logging.getLogger(__name__)


class GeminiError(RuntimeError):
    """A provider, response, or validation failure from the Gemini layer."""


class GeminiExplainer:
    def __init__(self, *, api_key: str, model: str, client: Any | None = None) -> None:
        if not client and not api_key.strip():
            raise ValueError("Gemini API key is required for the live explainer")
        self.model = model
        self._client = client
        self._api_key = api_key

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                from google import genai

                self._client = genai.Client(api_key=self._api_key)
            except Exception as exc:  # provider import/configuration is an external boundary
                raise GeminiError("unable to initialize Gemini client") from exc
        return self._client

    def explain(
        self,
        *,
        quantitative_context: Any,
        event_context: Any,
        decision_context: Any,
    ) -> GeminiExplanation:
        prompt = build_prompt(
            quantitative_context=quantitative_context,
            event_context=event_context,
            decision_context=decision_context,
        )
        try:
            from google.genai import types

            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=GeminiExplanation.model_json_schema(),
                    temperature=0.2,
                ),
            )
        except Exception as exc:  # network/API failures must be recoverable by the caller
            logger.warning("Gemini explanation failed", exc_info=True)
            raise GeminiError("Gemini request failed") from exc

        try:
            parsed = getattr(response, "parsed", None)
            if parsed is not None:
                return GeminiExplanation.model_validate(parsed)
            text = getattr(response, "text", None)
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Gemini returned no structured content")
            return GeminiExplanation.model_validate_json(text)
        except Exception as exc:
            logger.warning("Gemini returned invalid structured explanation", exc_info=True)
            raise GeminiError("Gemini response failed schema validation") from exc


def explanation_conflicts_with_signal(explanation: GeminiExplanation, signal: Signal) -> bool:
    """Flag explicit primary-signal contradictions without trusting prose as a decision source."""
    text = " ".join(
        (
            explanation.market_summary,
            explanation.technical_explanation,
            explanation.news_context,
            explanation.bull_case,
            explanation.bear_case,
            explanation.risk,
            explanation.conclusion,
        )
    ).lower()
    if signal == Signal.INSUFFICIENT_DATA:
        return "bullish" in text or "bearish" in text

    opposite = (
        "bearish"
        if signal == Signal.BULLISH
        else "bullish"
        if signal == Signal.BEARISH
        else None
    )
    if opposite is None:
        return False
    explicit_conflict_markers = (
        f"primary signal is {opposite}",
        f"signal: {opposite}",
        f"signal is {opposite}",
        f"conclusion: {opposite}",
    )
    return any(marker in text for marker in explicit_conflict_markers)
