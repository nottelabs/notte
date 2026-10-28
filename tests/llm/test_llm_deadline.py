"""A provider's keepalive bytes must not reset the HTTP attempt budget."""

import asyncio
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from aiohttp import web
from notte_core.errors import LLMProviderError
from notte_llm.engine import LLMEngine


class KeepaliveEndpoint:
    def __init__(self, slow_attempts: int) -> None:
        self.slow_attempts = slow_attempts
        self.requests = 0
        self.closed_streams = 0
        self.all_closed = asyncio.Event()
        self.started = asyncio.Event()

    async def handle(self, request: web.Request) -> web.StreamResponse:
        await request.read()
        self.requests += 1
        if self.requests > self.slow_attempts:
            return web.json_response({"choices": [{"message": {"content": "done"}}]})
        response = web.StreamResponse(headers={"Content-Type": "application/json"})
        await response.prepare(request)
        self.started.set()
        try:
            # Each read is fast; only a total deadline can stop this response.
            for _ in range(100):
                await response.write(b" ")
                await asyncio.sleep(0.01)
            await response.write(b'{"choices":[{"message":{"content":"late"}}]}')
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            self.closed_streams += 1
            if self.closed_streams == self.slow_attempts:
                self.all_closed.set()
        return response


@pytest_asyncio.fixture(loop_scope="function")
async def keepalive_endpoint(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[KeepaliveEndpoint]:
    slow_attempts, idle_connection = request.param
    endpoint = KeepaliveEndpoint(slow_attempts)
    app = web.Application()
    app.router.add_post("/v1/chat/completions", endpoint.handle)
    runner = web.AppRunner(app)
    await runner.setup()
    server = await asyncio.get_running_loop().create_server(runner.server, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    monkeypatch.setenv("NOTTE_LLM_BASE_URL", f"http://127.0.0.1:{port}/v1")
    monkeypatch.setenv("NOTTE_LLM_API_KEY", "test-key")
    monkeypatch.setattr("notte_llm.engine._TRANSIENT_RETRY_DELAYS_SECONDS", (0.0, 0.0))
    idle_reader: asyncio.StreamReader | None = None
    idle_writer: asyncio.StreamWriter | None = None
    if idle_connection:
        idle_reader, idle_writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        yield endpoint
    finally:
        server.close()
        try:
            # wait_closed() also waits for accepted connections. Drain aiohttp
            # first so an idle keepalive cannot deadlock fixture teardown.
            await runner.cleanup()
            await server.wait_closed()
            if idle_reader is not None:
                assert await idle_reader.read() == b""
        finally:
            if idle_writer is not None:
                idle_writer.close()
                await idle_writer.wait_closed()


@pytest.mark.asyncio
@pytest.mark.parametrize("keepalive_endpoint", [(1, False), (3, False), (1, True), (3, True)], indirect=True)
async def test_keepalive_responses_obey_each_attempt_deadline(keepalive_endpoint: KeepaliveEndpoint) -> None:
    engine = LLMEngine(model="test-model", timeout=0.1)
    if keepalive_endpoint.slow_attempts == 3:
        with pytest.raises(LLMProviderError, match="failed after retries"):
            await engine.completion([])
        assert keepalive_endpoint.requests == 3
    else:
        result = await engine.completion([])
        assert result["choices"][0]["message"]["content"] == "done"
        assert keepalive_endpoint.requests == 2
    await asyncio.wait_for(keepalive_endpoint.all_closed.wait(), timeout=1)
    assert keepalive_endpoint.closed_streams == keepalive_endpoint.slow_attempts


@pytest.mark.asyncio
@pytest.mark.parametrize("keepalive_endpoint", [(1, False), (1, True)], indirect=True)
async def test_caller_cancellation_closes_response_without_retry(keepalive_endpoint: KeepaliveEndpoint) -> None:
    task = asyncio.create_task(LLMEngine(model="test-model").completion([]))
    await asyncio.wait_for(keepalive_endpoint.started.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.wait_for(keepalive_endpoint.all_closed.wait(), timeout=1)
    assert keepalive_endpoint.requests == 1
