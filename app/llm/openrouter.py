from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import httpx

from app.llm.prompts import (
    build_openrouter_analyst_prompt,
    build_openrouter_judge_prompt,
)
from app.llm.schemas import PP10AIReport

logger = logging.getLogger(__name__)

RequestFn = Callable[..., httpx.Response]


class OpenRouterError(RuntimeError):
    """A provider, response, or validation failure from OpenRouter."""


@dataclass(frozen=True)
class OpenRouterCompletion:
    content: str
    model: str | None = None


class OpenRouterClient:
    """Small OpenRouter HTTP client using the OpenAI-compatible chat endpoint."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout_seconds: float = 45.0,
        data_collection: str = "deny",
        requester: RequestFn | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OpenRouter API key is required")
        if timeout_seconds <= 0:
            raise ValueError("OpenRouter timeout must be positive")
        if data_collection not in {"allow", "deny"}:
            raise ValueError("OpenRouter data collection must be allow or deny")
        self._api_key = api_key.strip()
        self._endpoint = f"{base_url.rstrip('/')}/chat/completions"
        self._timeout_seconds = timeout_seconds
        self._data_collection = data_collection
        self._requester = requester or self._request

    def _request(self, **kwargs: Any) -> httpx.Response:
        with httpx.Client(timeout=self._timeout_seconds) as client:
            return client.post(**kwargs)

    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        fallback_models: Sequence[str] = (),
        response_format: dict[str, Any] | None = None,
    ) -> OpenRouterCompletion:
        model = model.strip()
        if not model:
            raise ValueError("OpenRouter model is required")
        fallbacks = tuple(item.strip() for item in fallback_models if item.strip())
        payload: dict[str, Any] = {
            "messages": messages,
            "temperature": 0.2,
            "stream": False,
            "provider": {
                "require_parameters": response_format is not None,
                "data_collection": self._data_collection,
            },
        }
        if fallbacks:
            payload["models"] = [model, *fallbacks]
        else:
            payload["model"] = model
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if response_format is not None:
            payload["response_format"] = response_format

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = self._requester(url=self._endpoint, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise OpenRouterError("OpenRouter request failed") from exc
        if response.status_code >= 400:
            raise OpenRouterError(f"OpenRouter request failed with HTTP {response.status_code}")

        try:
            body = response.json()
            choices = body["choices"]
            message = choices[0]["message"]
            content = _message_content(message.get("content"))
            if not content:
                raise ValueError("response content is empty")
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise OpenRouterError("OpenRouter returned an invalid response") from exc
        return OpenRouterCompletion(content=content, model=body.get("model"))


_ANALYST_ROLES: tuple[str, ...] = (
    "Chuyên gia kỹ thuật",
    "Chuyên gia cấu trúc và mẫu hình",
    "Chuyên gia rủi ro và phản biện",
)


@dataclass(frozen=True)
class DebateDraft:
    role: str
    model: str
    content: str


class OpenRouterDebateExplainer:
    """Runs independent analyst calls in parallel and asks a judge for PP10 JSON."""

    display_name = "OpenRouter: hội đồng AI"

    def __init__(
        self,
        *,
        api_key: str,
        analyst_models: Sequence[str],
        judge_model: str,
        fallback_models: Sequence[str] = (),
        base_url: str = "https://openrouter.ai/api/v1",
        timeout_seconds: float = 45.0,
        max_parallel: int = 3,
        data_collection: str = "deny",
        judge_generator: Any | None = None,
        client: OpenRouterClient | None = None,
    ) -> None:
        models = tuple(item.strip() for item in analyst_models if item.strip())
        if not models:
            raise ValueError("At least one OpenRouter analyst model is required")
        if max_parallel <= 0:
            raise ValueError("OpenRouter max parallel must be positive")
        self.analyst_models = models[: len(_ANALYST_ROLES)]
        self.judge_model = judge_model.strip()
        if not self.judge_model:
            raise ValueError("OpenRouter judge model is required")
        self.fallback_models = tuple(item.strip() for item in fallback_models if item.strip())
        self.max_parallel = min(max_parallel, len(self.analyst_models))
        self.client = client or OpenRouterClient(
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            data_collection=data_collection,
        )
        self.judge_generator = judge_generator
        if judge_generator is None:
            self.model = self.judge_model
            self.display_name = "OpenRouter: hội đồng AI"
        else:
            self.model = getattr(judge_generator, "model", "Gemini Judge")
            self.display_name = "OpenRouter analyst + Gemini Judge"

    def generate_pp10_report(
        self,
        *,
        symbol: str,
        analysis_date: str,
        quantitative_context: Any | None = None,
    ) -> PP10AIReport:
        jobs = list(zip(_ANALYST_ROLES, self.analyst_models, strict=False))
        drafts: list[DebateDraft] = []
        with ThreadPoolExecutor(max_workers=self.max_parallel) as executor:
            futures = {
                executor.submit(
                    self._run_analyst,
                    role=role,
                    model=model,
                    symbol=symbol,
                    analysis_date=analysis_date,
                    quantitative_context=quantitative_context,
                ): (role, model)
                for role, model in jobs
            }
            for future in as_completed(futures):
                role, model = futures[future]
                try:
                    drafts.append(future.result())
                except Exception:
                    logger.warning(
                        "OpenRouter analyst failed role=%s model=%s",
                        role,
                        model,
                        exc_info=True,
                    )

        if not drafts:
            raise OpenRouterError("No OpenRouter analyst response")
        drafts.sort(key=lambda item: item.role)
        draft_payload = [
            {"role": draft.role, "model": draft.model, "content": draft.content}
            for draft in drafts
        ]
        if self.judge_generator is not None:
            return self.judge_generator.generate_pp10_report(
                symbol=symbol,
                analysis_date=analysis_date,
                quantitative_context=quantitative_context,
                debate_drafts=draft_payload,
            )
        judge_prompt = build_openrouter_judge_prompt(
            symbol=symbol,
            analysis_date=analysis_date,
            quantitative_context=quantitative_context,
            drafts=draft_payload,
        )
        completion = self.client.complete(
            model=self.judge_model,
            fallback_models=self.fallback_models,
            messages=[{"role": "user", "content": judge_prompt}],
            max_tokens=4000,
            response_format=_pp10_response_format(),
        )
        try:
            return _parse_pp10_report_text(completion.content)
        except Exception as exc:
            logger.warning("OpenRouter judge returned invalid PP10 report", exc_info=True)
            raise OpenRouterError("OpenRouter judge response failed schema validation") from exc

    def _run_analyst(
        self,
        *,
        role: str,
        model: str,
        symbol: str,
        analysis_date: str,
        quantitative_context: Any | None,
    ) -> DebateDraft:
        prompt = build_openrouter_analyst_prompt(
            role=role,
            symbol=symbol,
            analysis_date=analysis_date,
            quantitative_context=quantitative_context,
        )
        completion = self.client.complete(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1200,
        )
        return DebateDraft(
            role=role,
            model=completion.model or model,
            content=completion.content,
        )


class HybridReportGenerator:
    """Use a primary report generator and fall back to another provider on provider errors."""

    def __init__(self, *, primary: Any, fallback: Any | None = None) -> None:
        if primary is None:
            raise ValueError("Hybrid primary report generator is required")
        self.primary = primary
        self.fallback = fallback
        self.model = getattr(primary, "model", "hybrid")
        self.display_name = getattr(primary, "display_name", "AI hybrid")

    def generate_pp10_report(self, **kwargs: Any) -> PP10AIReport:
        try:
            return self.primary.generate_pp10_report(**kwargs)
        except OpenRouterError:
            if self.fallback is None:
                raise
            logger.warning(
                "Primary OpenRouter report failed; using fallback generator",
                exc_info=True,
            )
            return self.fallback.generate_pp10_report(**kwargs)


def _pp10_response_format() -> dict[str, Any]:
    schema = deepcopy(PP10AIReport.model_json_schema())
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "PP10AIReport",
            "strict": True,
            "schema": schema,
        },
    }


def _message_content(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [
            item.get("text", "")
            for item in value
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
        return "".join(parts).strip()
    return ""


def _parse_pp10_report_text(text: str) -> PP10AIReport:
    candidate = text.strip()
    if candidate.startswith("```"):
        first_newline = candidate.find("\n")
        if first_newline >= 0:
            candidate = candidate[first_newline + 1 :].strip()
        if candidate.endswith("```"):
            candidate = candidate[:-3].rstrip()

    start = candidate.find("{")
    if start < 0:
        raise ValueError("OpenRouter response does not contain a JSON object")
    payload, _ = json.JSONDecoder().raw_decode(candidate[start:])
    return PP10AIReport.model_validate(payload)
