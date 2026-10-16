"""Routes and HTTP observations shared by the live matrix and its offline contracts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import httpx
from notte_core.errors import LLMProviderError, RateLimitError


@dataclass(frozen=True)
class Route:
    name: str
    model: str
    upstream: str = ""


ROUTES = (
    Route("gemini", "google/gemini-3.5-flash-lite", "google-ai-studio"),
    Route("gemini-flash", "google/gemini-3.5-flash", "google-ai-studio"),
    Route("claude", "anthropic/claude-sonnet-4-5", "anthropic"),
    Route("openai", "openai/gpt-4o", "openai"),
    Route("groq", "openai/gpt-oss-120b", "groq"),
    Route("cerebras", "openai/gpt-oss-120b", "cerebras"),
    # Kimi has no Moonshot-hosted OpenRouter endpoint; pin an advertised upstream.
    Route("kimi", "moonshotai/kimi-k2.5", "novita"),
    Route("xai", "x-ai/grok-4.3", "xai"),
    Route("qwen", "qwen/qwen3.5-397b-a17b", "alibaba"),
    Route("minimax", "minimax/minimax-m2.5", "minimax"),
    Route("deepseek", "deepseek/deepseek-chat", "deepinfra"),
    Route("together", "meta-llama/llama-3.3-70b-instruct", "together"),
    Route("zai", "z-ai/glm-5.3-flash", "z-ai"),
    Route("vertex", "google/gemini-3.5-flash-lite"),
)
CASES = ("github_signin", "duckduckgo", "checkout/article", "instructions")


class UnavailableRoute(Exception):
    """No advertised candidate exists for an optional upstream pin."""


@lru_cache
def endpoints(model: str) -> list[dict[str, Any]]:
    response = httpx.get(f"https://openrouter.ai/api/v1/models/{model}/endpoints", timeout=30)
    # A removed optional model can be replaced by another advertised GLM candidate.
    if response.status_code == 404:
        return []
    response.raise_for_status()
    return response.json()["data"]["endpoints"]


def routing_options(route: Route) -> tuple[str, dict[str, Any]]:
    """Resolve the two formerly unavailable routes from the live catalog.

    Lookup errors propagate: an unavailable catalog must not silently hide coverage.
    An empty result specifically means no advertised upstream/model for the pin.
    """
    model = route.model
    options: dict[str, Any] = {
        "models": None,
        "provider": {"order": [route.upstream], "allow_fallbacks": False},
    }
    if route.name in {"together", "zai"}:
        candidates = (model, "z-ai/glm-5.3") if route.name == "zai" else (model,)
        for candidate in candidates:
            matching = [e for e in endpoints(candidate) if e["tag"].split("/")[0] == route.upstream]
            if matching:
                model = candidate
                # Together's Llama endpoint currently permits only 2048 output tokens.
                # Configure its advertised limit without changing the library default.
                limits = [e["max_completion_tokens"] for e in matching if e.get("max_completion_tokens")]
                if limits:
                    options["max_completion_tokens"] = min(8192, min(limits))
                break
        else:
            raise UnavailableRoute(f"OpenRouter catalog has no {route.upstream} endpoint for {', '.join(candidates)}")
    return model, options


@dataclass
class Attempt:
    path: str
    status: int | None = None
    error: str = ""
    provider: str = ""


@dataclass
class Trace:
    attempts: list[Attempt] = field(default_factory=list)

    def observe(self, request: httpx.Request) -> Attempt:
        body = json.loads(request.content)
        fmt = body.get("response_format", {}).get("type")
        attempt = Attempt(path="strict" if fmt == "json_schema" else fmt or "prompt-only")
        self.attempts.append(attempt)
        return attempt

    @staticmethod
    def response(attempt: Attempt, response: httpx.Response, key: str) -> None:
        attempt.status = response.status_code
        if response.status_code >= 400:
            attempt.error = response.text.replace(key, "[REDACTED]")
        try:
            payload = response.json()
        except ValueError:
            return
        if isinstance(payload, dict):
            attempt.provider = payload.get("provider", "")
            error = payload.get("error")
            if error is not None:
                attempt.error = json.dumps(error).replace(key, "[REDACTED]")
                if isinstance(error, dict) and isinstance(error.get("code"), int):
                    attempt.status = error["code"]

    def capacity_reason(self, error: Exception) -> str | None:
        # Parsing/schema/auth failures are never capacity skips, even after a retry.
        if isinstance(error, RateLimitError):
            return "HTTP 429: upstream rate limit after client retries"
        if type(error) is not LLMProviderError or not self.attempts:
            return None
        last = self.attempts[-1]
        if last.status in (429, 503):
            return f"HTTP {last.status}: upstream capacity exhausted after client retries: {last.error[:500]}"
        if last.error.endswith("Timeout"):
            return f"{last.error}: provider timed out after client retries"
        if last.status and last.status >= 500 and re.search(r"overload|capacity|engine_overloaded", last.error, re.I):
            return f"Upstream overloaded after client retries: {last.error[:500]}"
        return None
