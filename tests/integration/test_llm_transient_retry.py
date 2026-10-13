import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from notte_core.errors.provider import LLMProviderError
from notte_llm.engine import LLMEngine
from pydantic import BaseModel

# Real LiteLLM Gemini calls against a local server that speaks the Gemini API, so the
# provider's actual error mapping reaches the engine without a live outage.
OVERLOADED = (503, {"error": {"code": 503, "message": "This model is currently experiencing high demand.", "status": "UNAVAILABLE"}})
NO_CANDIDATES = (200, {"candidates": [], "usageMetadata": {"promptTokenCount": 1, "totalTokenCount": 1}})
ANSWER = (
    200,
    {
        "candidates": [
            {"content": {"role": "model", "parts": [{"text": '{"text": "done"}'}]}, "finishReason": "STOP", "index": 0}
        ],
        "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1, "totalTokenCount": 2},
    },
)


class Answer(BaseModel):
    text: str


class FakeGemini:
    """Answers each request with the next queued response, then with a valid answer."""

    def __init__(self, responses: list[tuple[int, dict[str, Any]]]) -> None:
        self.responses = list(responses)
        self.requests = 0
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                _ = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                fake.requests += 1
                status, body = fake.responses.pop(0) if fake.responses else ANSWER
                payload = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                _ = self.wfile.write(payload)

            def log_message(self, format: str, *args: Any) -> None:
                return None

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)


@pytest.fixture
def gemini(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeGemini]:
    fake = FakeGemini(request.param)
    thread = threading.Thread(target=fake.server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr("litellm.api_base", f"http://127.0.0.1:{fake.server.server_address[1]}")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("notte_llm.engine.enable_openrouter", lambda: False)

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("notte_llm.engine.asyncio.sleep", no_sleep)
    try:
        yield fake
    finally:
        fake.server.shutdown()
        fake.server.server_close()


MESSAGES: list[Any] = [{"role": "user", "content": 'Reply with {"text": "done"}'}]


@pytest.mark.asyncio
@pytest.mark.parametrize("gemini", [[OVERLOADED]], indirect=True)
async def test_overloaded_gemini_is_retried(gemini: FakeGemini):
    result = await LLMEngine(model="gemini/gemini-test").structured_completion(MESSAGES, Answer)

    assert result.text == "done"
    assert gemini.requests == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("gemini", [[NO_CANDIDATES]], indirect=True)
async def test_gemini_response_without_candidates_is_retried(gemini: FakeGemini):
    result = await LLMEngine(model="gemini/gemini-test").structured_completion(MESSAGES, Answer)

    assert result.text == "done"
    assert gemini.requests == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("gemini", [[OVERLOADED, OVERLOADED, OVERLOADED]], indirect=True)
async def test_persistent_gemini_overload_fails_after_the_retries(gemini: FakeGemini):
    with pytest.raises(LLMProviderError):
        _ = await LLMEngine(model="gemini/gemini-test").structured_completion(MESSAGES, Answer)

    assert gemini.requests == 3
