"""Routes and HTTP observations shared by the live matrix and its offline contracts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import httpx
from notte_core.errors import LLMProviderError, RateLimitError

from tests.flake_diagnostics import redact


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
    # OpenRouter's deepseek/deepseek-chat is the December 2024 V3 release, not an alias
    # for DeepSeek's current chat model. V4 Flash is DeepSeek's current non-thinking model.
    Route("deepseek", "deepseek/deepseek-v4-flash", "deepinfra"),
    Route("together", "meta-llama/llama-3.3-70b-instruct", "together"),
    Route("zai", "z-ai/glm-5.3-flash", "z-ai"),
    Route("vertex", "google/gemini-3.5-flash-lite", "google-vertex"),
)
CASES = ("github_signin", "duckduckgo", "checkout/article", "instructions")
EXTRACTION_INSTRUCTIONS = (
    "Extract the page title and the first three distinct Markdown links (label and URL) "
    "in document order, from anywhere in the document, including body and footer links. "
    "Count repeated URLs only once, using the first label. Ignore plain text without a link target. "
    "Copy each label exactly as written between the Markdown brackets, including punctuation and case. "
    "Copy each URL target exactly as provided. "
    "Include a short summary. Use null for missing optional descriptions."
)
# Ground truth from the saved scrape.md files, independent of provider output.
EXPECTED_LINKS = {
    "github_signin": (
        ("Skip to content", "https://github.com/login#start-of-content"),
        ("Reload", "https://github.com/login"),
        ("Forgot password?", "https://github.com/password_reset"),
    ),
    "duckduckgo": (
        ("Chat", "https://duck.ai/"),
        (
            "Add Extension",
            "https://addons.mozilla.org/firefox/downloads/latest/duckduckgo-for-firefox/addon-385621-latest.xpi",
        ),
        ("Mac", "https://duckduckgo.com/mac?origin=funnel_home___details"),
    ),
    "checkout/article": (
        ("Learn more.", "https://article.com/financing"),
        ("Article", "https://www.article.com/"),
        ("Terms of Use", "https://www.article.com/tou"),
    ),
}


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
    completion: str = field(default="", repr=False)


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
        try:
            _ = response.content
        except httpx.ResponseNotRead:
            # Observations must never consume a response stream for the caller.
            attempt.completion = "Response body was not cached"
            return
        if response.status_code >= 400:
            attempt.error = response.text.replace(key, "[REDACTED]")
        try:
            payload = response.json()
        except ValueError:
            return
        if isinstance(payload, dict):
            # Keep only completion fields, never echoed requests, headers or prompts.
            choices = payload.get("choices")
            if isinstance(choices, list):
                completions: list[dict[str, str | None]] = []
                for choice in choices:
                    if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
                        continue
                    message = choice["message"]
                    completions.append(
                        {
                            name: redact(value.replace(key, "[REDACTED]") if key else value)
                            if isinstance(value, str)
                            else None
                            for name, value in (
                                ("content", message.get("content")),
                                ("refusal", message.get("refusal")),
                                ("finish_reason", choice.get("finish_reason")),
                            )
                            if value is None or isinstance(value, str)
                        }
                    )
                text = json.dumps(completions)
                # Redact complete values before a cutoff could expose a secret prefix.
                attempt.completion = redact(text)[:64_000]
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
