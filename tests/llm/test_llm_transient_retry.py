import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from notte_core.errors import LLMProviderError
from notte_llm.engine import LLMEngine
from pydantic import BaseModel

# Real HTTP calls against a local OpenAI-compatible server exercise transport error mapping.
OVERLOADED = (
    503,
    {"error": {"code": 503, "message": "This model is currently experiencing high demand.", "status": "UNAVAILABLE"}},
)
NO_CANDIDATES = (200, {"choices": []})
ANSWER = (200, {"choices": [{"message": {"content": '{"text":"done"}'}}]})


class Answer(BaseModel):
    text: str


class FakeEndpoint:
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
def endpoint(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeEndpoint]:
    fake = FakeEndpoint(request.param)
    thread = threading.Thread(target=fake.server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("NOTTE_LLM_BASE_URL", f"http://127.0.0.1:{fake.server.server_address[1]}/v1")
    monkeypatch.setenv("NOTTE_LLM_API_KEY", "test-key")

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
@pytest.mark.parametrize("endpoint", [[OVERLOADED]], indirect=True)
async def test_overloaded_provider_is_retried(endpoint: FakeEndpoint):
    result = await LLMEngine(model="test-model").structured_completion(MESSAGES, Answer)

    assert result.text == "done"
    assert endpoint.requests == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", [[NO_CANDIDATES]], indirect=True)
async def test_response_without_choices_is_retried(endpoint: FakeEndpoint):
    result = await LLMEngine(model="test-model").structured_completion(MESSAGES, Answer)

    assert result.text == "done"
    assert endpoint.requests == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", [[OVERLOADED, OVERLOADED, OVERLOADED]], indirect=True)
async def test_persistent_provider_overload_fails_after_the_retries(endpoint: FakeEndpoint):
    with pytest.raises(LLMProviderError):
        _ = await LLMEngine(model="test-model").structured_completion(MESSAGES, Answer)

    assert endpoint.requests == 3
