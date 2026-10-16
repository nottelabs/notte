"""Offline contracts that keep capacity skips from hiding client regressions."""

import json

import httpx
import pytest
from notte_core.errors import InvalidAPIKeyError, LLMParsingError, LLMProviderError
from notte_llm import LlmExtractor
from pydantic import BaseModel

from tests.llm.provider_matrix import ROUTES, Attempt, Route, Trace, UnavailableRoute, routing_options


@pytest.mark.parametrize("status", [400, 401, 404, 422, 500, 502])
def test_request_and_unclassified_provider_failures_are_not_capacity_skips(status):
    error = LLMProviderError(dev_message="request failed", user_message="failed", agent_message=None)
    assert Trace([Attempt("strict", status=status)]).capacity_reason(error) is None


@pytest.mark.parametrize("status", [429, 503])
def test_capacity_status_only_skips_provider_errors(status):
    trace = Trace([Attempt("strict", status=status)])
    error = LLMProviderError(dev_message="capacity", user_message="capacity", agent_message=None)
    assert trace.capacity_reason(error)
    assert trace.capacity_reason(LLMParsingError("invalid JSON")) is None
    assert trace.capacity_reason(InvalidAPIKeyError(provider="test")) is None


def test_recovered_capacity_error_does_not_hide_parse_failure():
    trace = Trace([Attempt("strict", status=503), Attempt("strict", status=200)])
    assert trace.capacity_reason(LLMParsingError("invalid JSON")) is None
    error = LLMProviderError(dev_message="malformed choices", user_message="failed", agent_message=None)
    assert trace.capacity_reason(error) is None


def test_timeout_after_retries_is_capacity_but_connection_errors_are_not():
    error = LLMProviderError(dev_message="retries exhausted", user_message="failed", agent_message=None)
    assert Trace([Attempt("strict", error="ReadTimeout")]).capacity_reason(error)
    assert Trace([Attempt("strict", error="ConnectError")]).capacity_reason(error) is None


@pytest.mark.parametrize(
    "status,message,capacity",
    [(502, "upstream overloaded", True), (502, "bad gateway", False), (400, "overloaded", False)],
)
def test_non_json_error_text_is_redacted_and_classified(status, message, capacity):
    trace = Trace([Attempt("strict")])
    trace.response(trace.attempts[-1], httpx.Response(status, text=f"{message}: test-key"), "test-key")
    error = LLMProviderError(dev_message="request failed", user_message="failed", agent_message=None)
    assert bool(trace.capacity_reason(error)) is capacity
    assert "test-key" not in trace.attempts[-1].error
    assert "[REDACTED]" in trace.attempts[-1].error


def test_endpoint_catalog_drives_together_limit_and_unavailable_pin(monkeypatch):
    monkeypatch.setattr(
        "tests.llm.provider_matrix.endpoints",
        lambda _: [{"tag": "together", "max_completion_tokens": 2048}],
    )
    model, options = routing_options(Route("together", "meta-llama/llama-3.3-70b-instruct", "together"))
    assert model == "meta-llama/llama-3.3-70b-instruct"
    assert options["max_completion_tokens"] == 2048
    assert options["provider"] == {"order": ["together"], "allow_fallbacks": False}
    assert options["models"] is None
    monkeypatch.setattr("tests.llm.provider_matrix.endpoints", lambda _: [])
    with pytest.raises(UnavailableRoute, match="no together endpoint"):
        routing_options(Route("together", model, "together"))


@pytest.mark.asyncio
@pytest.mark.parametrize("instructions_only", [False, True])
async def test_extractor_request_overrides_are_per_call(instructions_only, monkeypatch):
    class Title(BaseModel):
        title: str

    monkeypatch.setenv("NOTTE_LLM_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("NOTTE_LLM_API_KEY", "test-key")
    monkeypatch.delenv("NOTTE_LLM_MODEL", raising=False)
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"success":true,"data":{"title":"Hello"}}'}}]}
        )

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: original_client(**{**kwargs, "transport": httpx.MockTransport(handler)})
    )
    extractor = LlmExtractor()
    options = {
        "models": None,
        "provider": {"order": ["together"], "allow_fallbacks": False},
        "max_completion_tokens": 2048,
    }
    for extra in (options, None):
        result = await extractor.extract(
            url="https://example.com",
            document="# Hello",
            response_format=None if instructions_only else Title,
            instructions="Extract the title",
            model="meta-llama/llama-3.3-70b-instruct",
            extra_body=extra,
        )
        assert result.success
    assert "models" not in bodies[0]
    assert bodies[0]["provider"] == options["provider"]
    assert bodies[0]["max_completion_tokens"] == 2048
    assert bodies[1]["models"][0] == "meta-llama/llama-3.3-70b-instruct"
    assert "provider" not in bodies[1]
    assert bodies[1]["max_completion_tokens"] == 8192
    assert options["models"] is None


def test_matrix_keeps_default_flash_lite_and_additional_flash_route():
    routes = {route.name: route for route in ROUTES}
    assert len(routes) == 14
    assert routes["gemini"].model == "google/gemini-3.5-flash-lite"
    assert routes["gemini-flash"].model == "google/gemini-3.5-flash"
    assert routes["vertex"].model == "google/gemini-3.5-flash-lite"
