"""OpenAI-compatible chat completions client."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import requests

from app.config.settings import LLMSettings
from app.logging import get_logger, log_event

logger = get_logger(__name__)


class LLMError(RuntimeError):
    pass


@runtime_checkable
class LLMClient(Protocol):
    def complete(self, messages: list[dict[str, str]], *, temperature: float | None = None) -> str:
        ...


class OpenAICompatibleClient:
    def __init__(self, settings: LLMSettings, api_key: str | None) -> None:
        self.settings = settings
        self.api_key = api_key
        self.timeout = settings.timeout_seconds

    def complete(self, messages: list[dict[str, str]], *, temperature: float | None = None) -> str:
        if not self.api_key:
            raise LLMError(
                "OPENAI_API_KEY is not set. Add it to .env or the environment to use AI optimization."
            )

        url = self.settings.base_url.rstrip("/") + "/chat/completions"
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "temperature": self.settings.temperature if temperature is None else temperature,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        log_event(
            logger,
            "llm_request_started",
            provider=self.settings.provider,
            model=self.settings.model,
            base_url=self.settings.base_url,
        )
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc

        if response.status_code >= 400:
            raise LLMError(
                f"LLM API error {response.status_code}: {response.text[:500]}"
            )

        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected LLM response shape: {data}") from exc

        if not content:
            raise LLMError("LLM returned empty content")

        log_event(logger, "llm_request_completed", model=self.settings.model)
        return content
