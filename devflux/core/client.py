"""LLM Client — httpx-based, OpenAI-compatible, with reasoning_content fallback."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from .config import DevFluxConfig
from .credentials import CredentialsStore


@dataclass
class LLMResponse:
    """Response from an LLM call."""
    content: str
    reasoning: str = ""
    tokens: int = 0
    elapsed: float = 0.0
    raw: dict[str, Any] | None = None


class LLMClient:
    """OpenAI-compatible chat completions client (httpx)."""

    def __init__(self, config: DevFluxConfig, creds: CredentialsStore) -> None:
        self._config = config
        self._creds = creds
        self._client = httpx.Client(timeout=300.0, follow_redirects=True)

    @property
    def model(self) -> str:
        return self._config.model

    @property
    def base_url(self) -> str:
        return self._config.base_url

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        key = self._creds.get(self._config.provider)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Call /chat/completions endpoint. Returns LLMResponse."""
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self._config.temperature,
            "max_tokens": max_tokens or self._config.max_tokens,
            "stream": False,
        }
        start = time.time()
        resp = self._client.post(url, json=payload, headers=self._headers())
        elapsed = time.time() - start

        # Raise on HTTP errors
        resp.raise_for_status()
        data = resp.json()

        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        content = msg.get("content", "")
        # Lesson 15: reasoning_content fallback — merge into content if empty
        reasoning = msg.get("reasoning_content", "")
        if not content and reasoning:
            content = reasoning

        usage = data.get("usage", {})
        tokens = usage.get("total_tokens", 0)

        return LLMResponse(
            content=content.strip(),
            reasoning=reasoning,
            tokens=tokens,
            elapsed=elapsed,
            raw=data,
        )

    def list_models(self) -> list[str]:
        """List available models from /models endpoint."""
        try:
            url = f"{self.base_url.rstrip('/')}/models"
            resp = self._client.get(url, headers=self._headers(), timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
            return [m.get("id", m.get("name", "")) for m in data.get("data", [])]
        except Exception:
            return []

    def close(self) -> None:
        self._client.close()