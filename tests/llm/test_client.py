import json

import httpx
import pytest
from notte_core.errors import (
    ContentFilterError,
    ContextWindowExceededError,
    InsufficentCreditsError,
    InvalidAPIKeyError,
    InvalidJsonResponseForStructuredOutput,
    LLMProviderError,
    ModelNotFoundError,
    RateLimitError,
    UnsupportedResponseSchemaError,
)
from notte_llm.engine import LLMEngine


@pytest.fixture(autouse=True)
def endpoint(monkeypatch):
    monkeypatch.setenv("NOTTE_LLM_BASE_URL", "https://example.com/v1/")
    monkeypatch.setenv("NOTTE_LLM_API_KEY", "test-key")
    monkeypatch.setenv("NOTTE_LLM_MODEL", "native/model")


@pytest.mark.asyncio
async def test_completion_posts_compatible_payload_and_returns_response():
    def handler(request):
        assert request.method == "POST"
        assert str(request.url) == "https://example.com/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.extensions["timeout"] == dict(connect=60.0, read=60.0, write=60.0, pool=60.0)
        assert json.loads(request.content) == {
            "model": "native/model",
            "messages": [{"role": "user", "content": "Hello"}],
            "temperature": 0.5,
            "max_completion_tokens": 8192,
            "n": 1,
            "response_format": {"type": "json_object"},
        }
        return httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}], "usage": {"total_tokens": 1}})

    engine = LLMEngine(transport=httpx.MockTransport(handler))
    result = await engine.completion(
        [{"role": "user", "content": "Hello"}], temperature=0.5, response_format={"type": "json_object"}
    )
    assert result["choices"][0]["message"]["content"] == "hello"
    assert result["usage"]["total_tokens"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,message,error",
    [
        (401, "Unauthorized", InvalidAPIKeyError),
        (403, "Forbidden", InvalidAPIKeyError),
        # content refusals are not authentication failures
        (403, "Upstream error: content_policy_violation", ContentFilterError),
        (400, "Your request was rejected by our content_filter", ContentFilterError),
        (403, "Your chosen model requires moderation and your input was flagged", ContentFilterError),
        (404, "Model missing", ModelNotFoundError),
        (429, "Rate limit", RateLimitError),
        (400, "context_length_exceeded", ContextWindowExceededError),
        (400, "Current length is 123 while limit is 100", ContextWindowExceededError),
        (400, "invalid JSON schema for response_format", UnsupportedResponseSchemaError),
        (422, "response_format unsupported", UnsupportedResponseSchemaError),
        (400, "Invalid JSON response", InvalidJsonResponseForStructuredOutput),
        (402, "Insufficient balance", InsufficentCreditsError),
        (400, "max_tokens is too large", LLMProviderError),
        (500, "internal error", LLMProviderError),
    ],
)
async def test_error_mapping(status, message, error, monkeypatch):
    delays = []

    async def sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr("notte_llm.engine.asyncio.sleep", sleep)
    engine = LLMEngine(
        transport=httpx.MockTransport(lambda _: httpx.Response(status, json={"error": {"message": message}}))
    )
    with pytest.raises(error) as exc:
        await engine.completion([])
    assert type(exc.value) is error
    assert delays == ([2.0, 5.0] if status == 429 or status >= 500 else [])
    if "Current length" in message:
        assert "123" in str(exc.value) and "100" in str(exc.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
async def test_transient_error_then_success(status, monkeypatch):
    attempts = []
    delays = []

    async def sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr("notte_llm.engine.asyncio.sleep", sleep)

    def handler(request):
        attempts.append(request)
        return (
            httpx.Response(status, json={"error": {"message": "temporary"}})
            if len(attempts) < 3
            else httpx.Response(200, json={"choices": []})
        )

    assert await LLMEngine(transport=httpx.MockTransport(handler)).completion([]) == {"choices": []}
    assert len(attempts) == 3
    assert delays == [2.0, 5.0]


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [httpx.ReadTimeout, httpx.ConnectError, httpx.RemoteProtocolError])
async def test_transport_errors_retry_and_hide_credentials(error, monkeypatch):
    attempts = []

    async def sleep(_):
        pass

    monkeypatch.setattr("notte_llm.engine.asyncio.sleep", sleep)

    def handler(request):
        attempts.append(request)
        raise error("test-key", request=request)

    with pytest.raises(LLMProviderError) as exc:
        await LLMEngine(transport=httpx.MockTransport(handler)).completion([])
    assert len(attempts) == 3
    assert exc.value.should_retry_later
    assert "test-key" not in str(exc.value)
    assert exc.value.__suppress_context__


@pytest.mark.asyncio
async def test_http_200_embedded_gateway_error_is_mapped(monkeypatch):
    async def sleep(_):
        pass

    monkeypatch.setattr("notte_llm.engine.asyncio.sleep", sleep)
    engine = LLMEngine(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"error": {"code": 429, "message": "rate limit"}})
        )
    )
    with pytest.raises(RateLimitError):
        await engine.completion([])


@pytest.mark.asyncio
async def test_non_json_provider_error_is_mapped_and_redacted():
    engine = LLMEngine(transport=httpx.MockTransport(lambda _: httpx.Response(400, text="invalid request test-key")))
    with pytest.raises(LLMProviderError) as exc:
        await engine.completion([])
    assert "[REDACTED]" in str(exc.value)
    assert "test-key" not in str(exc.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body", [{}, [], {"choices": "invalid"}, {"choices": [{}]}, {"choices": [None]}, {"choices": [{"message": None}]}]
)
async def test_malformed_response_is_a_provider_error(body):
    engine = LLMEngine(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body)))
    with pytest.raises(LLMProviderError):
        await engine.completion([])


OPENROUTER_REFUSAL = {
    "error": {
        "message": "Upstream error from Inception: I'm sorry, I can't help with that.",
        "code": 403,
        "metadata": {"error_type": "content_policy_violation", "provider_code": "content_filter"},
    }
}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        # OpenRouter: the HTTP status, or the same error embedded in a 200 body
        httpx.Response(403, json=OPENROUTER_REFUSAL),
        httpx.Response(200, json=OPENROUTER_REFUSAL),
        # OpenAI
        httpx.Response(
            400,
            json={
                "error": {
                    "message": "Your request was rejected",
                    "type": "invalid_request_error",
                    "code": "content_policy_violation",
                }
            },
        ),
        # Azure
        httpx.Response(
            400, json={"error": {"code": "content_filter", "innererror": {"code": "ResponsibleAIPolicyViolation"}}}
        ),
        # a successful response the provider filtered
        httpx.Response(200, json={"choices": [{"message": {"content": None}, "finish_reason": "content_filter"}]}),
    ],
)
async def test_content_refusals_are_not_api_key_errors(response: httpx.Response) -> None:
    engine = LLMEngine(model="inception/mercury-2.5", transport=httpx.MockTransport(lambda _: response))
    with pytest.raises(ContentFilterError) as exc:
        await engine.completion([])
    assert not isinstance(exc.value, InvalidAPIKeyError)
    assert exc.value.model == "inception/mercury-2.5" and "inception/mercury-2.5" in str(exc.value)


@pytest.mark.asyncio
async def test_content_refusal_reaches_structured_callers() -> None:
    """Extraction (`structured_completion`) surfaces the refusal instead of retrying or parsing."""
    from pydantic import BaseModel

    class Title(BaseModel):
        title: str

    calls: list[int] = []

    def handler(_: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(403, json=OPENROUTER_REFUSAL)

    engine = LLMEngine(transport=httpx.MockTransport(handler))
    with pytest.raises(ContentFilterError):
        _ = await engine.structured_completion([{"role": "user", "content": "x"}], Title)
    assert len(calls) == 1
