from __future__ import annotations

import json
import logging
from copy import deepcopy
from typing import Any

from app.domain.enums import Signal
from app.llm.prompts import build_chat_prompt, build_prompt
from app.llm.schemas import GeminiExplanation

logger = logging.getLogger(__name__)
_MIN_GEMINI_TIMEOUT_SECONDS = 10.0


def _gemini_response_schema() -> dict[str, Any]:
    schema = deepcopy(GeminiExplanation.model_json_schema())
    return _remove_unsupported_schema_fields(schema)


def _remove_unsupported_schema_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _remove_unsupported_schema_fields(item)
            for key, item in value.items()
            if key != "additionalProperties"
        }
    if isinstance(value, list):
        return [_remove_unsupported_schema_fields(item) for item in value]
    return value


class GeminiError(RuntimeError):
    """A provider, response, or validation failure from the Gemini layer."""


class GeminiExplainer:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        client: Any | None = None,
        timeout_seconds: float = 8.0,
    ) -> None:
        if not client and not api_key.strip():
            raise ValueError("Gemini API key is required for the live explainer")
        if timeout_seconds <= 0:
            raise ValueError("Gemini timeout must be positive")
        self.model = model
        self._client = client
        self._api_key = api_key
        self._timeout_ms = int(max(_MIN_GEMINI_TIMEOUT_SECONDS, timeout_seconds) * 1000)

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                from google import genai
                from google.genai import types

                self._client = genai.Client(
                    api_key=self._api_key,
                    http_options=types.HttpOptions(timeout=self._timeout_ms),
                )
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
                    response_schema=_gemini_response_schema(),
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
            return _parse_explanation_text(text)
        except Exception as exc:
            logger.warning("Gemini returned invalid structured explanation", exc_info=True)
            raise GeminiError("Gemini response failed schema validation") from exc

    def chat(self, message: str) -> str:
        prompt = build_chat_prompt(message)
        try:
            from google.genai import types

            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.4),
            )
        except Exception as exc:  # network/API failures must be recoverable by the caller
            logger.warning("Gemini chat failed", exc_info=True)
            raise GeminiError("Gemini chat request failed") from exc

        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise GeminiError("Gemini chat returned no text")
        return text.strip()


def _parse_explanation_text(text: str) -> GeminiExplanation:
    """Parse JSON even when a provider wraps it in Markdown or short prose."""
    candidate = text.strip()
    if candidate.startswith("```"):
        first_newline = candidate.find("\n")
        if first_newline >= 0:
            candidate = candidate[first_newline + 1 :].strip()
        if candidate.endswith("```"):
            candidate = candidate[:-3].rstrip()

    start = candidate.find("{")
    if start < 0:
        raise ValueError("Gemini response does not contain a JSON object")
    payload, _ = json.JSONDecoder().raw_decode(candidate[start:])
    return GeminiExplanation.model_validate(payload)


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
