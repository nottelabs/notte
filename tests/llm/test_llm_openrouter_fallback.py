import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from notte_llm.engine import LLMEngine
from pydantic import BaseModel


class Answer(BaseModel):
    text: str


class FakeOpenRouter:
    """OpenAI-compatible endpoint that records each request body and answers successfully."""

    def __init__(self) -> None:
        self.bodies: list[dict[str, Any]] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                fake.bodies.append(json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)))))
                payload = json.dumps(
                    {
                        "id": "gen-test",
                        "object": "chat.completion",
                        "created": 0,
                        "model": "google/gemini-3.8-flash",
                        "choices": [
                            {
                                "index": 0,
                                "message": {"role": "assistant", "content": '{"text": "done"}'},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                _ = self.wfile.write(payload)

            def log_message(self, format: str, *args: Any) -> None:
                return None

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)


@pytest.fixture
def openrouter(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeOpenRouter]:
    fake = FakeOpenRouter()
    thread = threading.Thread(target=fake.server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("NOTTE_LLM_BASE_URL", f"http://127.0.0.1:{fake.server.server_address[1]}/api/v1")
    monkeypatch.setenv("NOTTE_LLM_API_KEY", "test-key")
    try:
        yield fake
    finally:
        fake.server.shutdown()
        fake.server.server_close()


@pytest.mark.asyncio
async def test_local_compatible_server_receives_native_model(openrouter: FakeOpenRouter):
    messages: list[Any] = [{"role": "user", "content": 'Reply with {"text": "done"}'}]

    result = await LLMEngine(model="google/gemini-3.5-flash").structured_completion(messages, Answer)

    assert result.text == "done"
    body = openrouter.bodies[-1]
    assert body["model"] == "google/gemini-3.5-flash"
    # OpenRouter moves to the next model in this list when the requested one errors.
    # A custom host must receive only standard Chat Completions parameters.
    assert "models" not in body
