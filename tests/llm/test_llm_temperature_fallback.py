"""A provider that only accepts the default temperature gets a retry without the field."""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from notte_llm.engine import LLMEngine

TEMPERATURE_ERROR = (
    400,
    {
        "error": {
            "message": "Unsupported value: 'temperature' does not support 0.0 with this model. Only the default (1) value is supported.",
            "type": "invalid_request_error",
        }
    },
)
ANSWER = (
    200,
    {"choices": [{"message": {"content": '{"text":"done"}'}, "finish_reason": "stop"}]},
)


class FakeEndpoint:
    """Records request bodies and answers the queued responses before the answer."""

    def __init__(self) -> None:
        self.bodies: list[dict[str, Any]] = []
        self.responses: list[tuple[int, dict[str, Any]]] = [TEMPERATURE_ERROR]
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                fake.bodies.append(json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)))))
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
def endpoint(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeEndpoint]:
    fake = FakeEndpoint()
    thread = threading.Thread(target=fake.server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("NOTTE_LLM_BASE_URL", f"http://127.0.0.1:{fake.server.server_address[1]}/v1")
    monkeypatch.setenv("NOTTE_LLM_API_KEY", "test-key")
    yield fake
    fake.server.shutdown()


@pytest.mark.asyncio
async def test_rejected_temperature_is_retried_and_remembered(endpoint: FakeEndpoint) -> None:
    engine = LLMEngine(model="gpt-5.5")

    payload = await engine.completion([{"role": "user", "content": "hi"}], temperature=0.0)

    assert payload["choices"][0]["message"]["content"] == '{"text":"done"}'
    assert len(endpoint.bodies) == 2
    assert endpoint.bodies[0]["temperature"] == 0.0
    assert "temperature" not in endpoint.bodies[1]

    # Later calls to the same endpoint and model leave the field out from the start.
    await LLMEngine(model="gpt-5.5").completion([{"role": "user", "content": "hi"}], temperature=0.0)

    assert len(endpoint.bodies) == 3
    assert "temperature" not in endpoint.bodies[2]
