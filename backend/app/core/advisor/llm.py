"""Pluggable LLM backend for the AI advisor.

Supported providers:
- ``anthropic``         — Claude API (messages)
- ``openai``            — OpenAI API (chat.completions)
- ``openai_compatible`` — any server with OpenAI-compatible /v1/chat/completions (e.g. vLLM, LM Studio)
- ``ollama``            — local Ollama at /api/chat (default: gemma3:4b)
- ``none``              — no LLM layer; advisor runs rules-only

The provider is selected per user via ``advisor_llm_configs`` (falls back to
global settings). All calls are async and reuse the shared httpx client.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.db.models.advisor import AdvisorLLMConfig, AdvisorLLMProvider
from app.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class LLMRequest:
    system: str
    user: str
    temperature: float = 0.2
    max_tokens: int = 1024


@dataclass(frozen=True)
class LLMResponse:
    text: str
    provider: str
    model: str
    raw: dict[str, Any] | None = None


class LLMBackend(Protocol):
    provider: str
    model: str

    async def complete(self, req: LLMRequest) -> LLMResponse: ...


class NoOpBackend:
    provider = "none"
    model = "-"

    async def complete(self, req: LLMRequest) -> LLMResponse:
        return LLMResponse(text="", provider=self.provider, model=self.model)


class AnthropicBackend:
    provider = "anthropic"

    def __init__(self, *, http: httpx.AsyncClient, model: str, api_key: str, timeout_s: int = 120):
        self.http = http
        self.model = model
        self._api_key = api_key
        self._timeout = timeout_s

    async def complete(self, req: LLMRequest) -> LLMResponse:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": self.model,
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
            "system": req.system,
            "messages": [{"role": "user", "content": req.user}],
        }
        resp = await self.http.post(url, headers=headers, json=body, timeout=self._timeout)
        resp.raise_for_status()
        data = resp.json()
        text = "".join(
            block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
        )
        return LLMResponse(text=text, provider=self.provider, model=self.model, raw=data)


class OpenAIBackend:
    provider = "openai"

    def __init__(
        self,
        *,
        http: httpx.AsyncClient,
        model: str,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_s: int = 120,
    ):
        self.http = http
        self.model = model
        self._api_key = api_key
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s

    async def complete(self, req: LLMRequest) -> LLMResponse:
        url = f"{self._base}/chat/completions"
        headers = {
            "authorization": f"Bearer {self._api_key}",
            "content-type": "application/json",
        }
        body = {
            "model": self.model,
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
            "messages": [
                {"role": "system", "content": req.system},
                {"role": "user", "content": req.user},
            ],
        }
        resp = await self.http.post(url, headers=headers, json=body, timeout=self._timeout)
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        return LLMResponse(text=text, provider=self.provider, model=self.model, raw=data)


class OpenAICompatibleBackend(OpenAIBackend):
    """OpenAI-compatible endpoints (vLLM, LM Studio, LiteLLM, etc.)."""

    provider = "openai_compatible"


class OllamaBackend:
    """Local Ollama server (https://github.com/ollama/ollama).

    Works great with Gemma: pull once with ``ollama pull gemma3:4b`` and set
    ``DHRUVA_ADVISOR_LLM_MODEL=gemma3:4b``.
    """

    provider = "ollama"

    def __init__(
        self,
        *,
        http: httpx.AsyncClient,
        model: str,
        base_url: str = "http://localhost:11434",
        timeout_s: int = 120,
    ):
        self.http = http
        self.model = model
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s

    async def complete(self, req: LLMRequest) -> LLMResponse:
        url = f"{self._base}/api/chat"
        body = {
            "model": self.model,
            "stream": False,
            "options": {
                "temperature": req.temperature,
                "num_predict": req.max_tokens,
            },
            "messages": [
                {"role": "system", "content": req.system},
                {"role": "user", "content": req.user},
            ],
        }
        resp = await self.http.post(url, json=body, timeout=self._timeout)
        resp.raise_for_status()
        data = resp.json()
        text = data.get("message", {}).get("content", "")
        return LLMResponse(text=text, provider=self.provider, model=self.model, raw=data)


def build_backend(
    *,
    http: httpx.AsyncClient,
    provider: AdvisorLLMProvider | str,
    model: str,
    base_url: str,
    api_key: str | None,
    timeout_s: int,
) -> LLMBackend:
    p = provider.value if isinstance(provider, AdvisorLLMProvider) else provider
    if p == "none":
        return NoOpBackend()
    if p == "anthropic":
        if not api_key:
            logger.warning("advisor.llm.anthropic_missing_key")
            return NoOpBackend()
        return AnthropicBackend(http=http, model=model, api_key=api_key, timeout_s=timeout_s)
    if p == "openai":
        if not api_key:
            logger.warning("advisor.llm.openai_missing_key")
            return NoOpBackend()
        return OpenAIBackend(http=http, model=model, api_key=api_key, timeout_s=timeout_s)
    if p == "openai_compatible":
        return OpenAICompatibleBackend(
            http=http,
            model=model,
            api_key=api_key or "local",
            base_url=base_url or "http://localhost:8000/v1",
            timeout_s=timeout_s,
        )
    if p == "ollama":
        return OllamaBackend(
            http=http,
            model=model,
            base_url=base_url or "http://localhost:11434",
            timeout_s=timeout_s,
        )
    raise ValueError(f"unknown_llm_provider: {p}")


def backend_from_config(
    *, http: httpx.AsyncClient, config: AdvisorLLMConfig | None, fallback: dict[str, Any]
) -> LLMBackend:
    if config is not None and config.is_enabled:
        return build_backend(
            http=http,
            provider=config.provider,
            model=config.model,
            base_url=config.base_url,
            api_key=config.api_key_encrypted,  # decrypted by caller if needed
            timeout_s=fallback.get("timeout_s", 120),
        )
    return build_backend(
        http=http,
        provider=fallback["provider"],
        model=fallback["model"],
        base_url=fallback["base_url"],
        api_key=fallback.get("api_key"),
        timeout_s=fallback.get("timeout_s", 120),
    )


def parse_llm_json(text: str) -> dict[str, Any] | None:
    """Best-effort extraction of a JSON object from an LLM response.

    Local models often wrap JSON in markdown or prose; we scan for the first
    balanced ``{...}`` block.
    """
    if not text:
        return None
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None
