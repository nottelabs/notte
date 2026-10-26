"""The async transport behaves like the sync one: retries, deadlines, redirects, exceptions and TLS
recovery are compared by running the same scenario through `BaseClient` and `AsyncBaseClient`.
Its own lifecycle (one pooled client, event-loop binding, fork, close) is tested at the end.
"""

import asyncio
import gc
import json
import os
import random
import signal
import socket
import ssl
import threading
import time
import warnings
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

import httpcore
import httpx
import pytest
import requests
from notte_sdk import AsyncNotteClient, NotteClient
from notte_sdk._transport import (
    AsyncSharedHttpClient,
    SharedHttpClient,
    _AsyncHandshakeBackend,
    _AsyncHandshakeStream,
    aiter_lines,
    asend,
    astream,
    async_http_client,
    http_client,
    iter_lines,
    send,
)
from notte_sdk.endpoints.base import AsyncBaseClient, BaseClient, NotteEndpoint, _ClientCore
from notte_sdk.errors import (
    NotteAPIError,
    NotteConnectionError,
    NotteInvalidURLError,
    NotteRequestError,
    NotteRequestTimeoutError,
    NotteSSLError,
)
from pydantic import BaseModel

from tests.sdk.test_handshake_transport import (  # noqa: F401
    PROXY_VARIABLES,
    FakeStream,
    certificate,
    handshake_failure,
    tls_server,
)
from tests.sdk.test_httpx_transport import keep_alive_server  # noqa: F401

SERVER = "https://api.example.test"
KEY = "test-key"  # pragma: allowlist secret


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("fail", [False, True])
async def test_thread_call_settles_and_preserves_its_outcome(cancel: bool, fail: bool) -> None:
    from notte_sdk._transport import athread

    started, release, settled = threading.Event(), threading.Event(), threading.Event()

    def operation(value: int, *, increment: int) -> int:
        started.set()
        assert release.wait(5)
        settled.set()
        if fail:
            raise ValueError("worker failed")
        return value + increment

    task = asyncio.create_task(athread(operation, 40, increment=2))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        if cancel:
            for _ in range(2):
                task.cancel()
                await asyncio.sleep(0)
                assert not task.done()
        release.set()
        if cancel:
            with pytest.raises(asyncio.CancelledError):
                await task
        elif fail:
            with pytest.raises(ValueError, match="worker failed"):
                await task
        else:
            assert await task == 42
        assert settled.is_set()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_ClientCore, "check_and_warn_version_mismatch", lambda _: None)
    for name in (*PROXY_VARIABLES, "NO_PROXY", "no_proxy", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        monkeypatch.delenv(name, raising=False)


class Clock:
    """Monotonic time for the transport, advanced by its sync and async sleeps."""

    def __init__(self, step: float | None = None) -> None:
        self.now: float = 0.0
        self.sleeps: list[float] = []
        # A sleep advances the clock by its delay, or by `step` to overshoot a deadline.
        self.step: float | None = step

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds if self.step is None else self.step

    async def asleep(self, seconds: float) -> None:
        self.sleep(seconds)


def use_clock(monkeypatch: pytest.MonkeyPatch, clock: Clock) -> None:
    """Give the transport module `clock` as its time; nothing else sees it."""
    monkeypatch.setattr("notte_sdk._transport.time", SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep))
    monkeypatch.setattr(
        "notte_sdk._transport.asyncio", SimpleNamespace(sleep=clock.asleep, get_running_loop=asyncio.get_running_loop)
    )


class Raising(httpx.SyncByteStream, httpx.AsyncByteStream):
    """A body that fails after its first chunk, for either client."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def __iter__(self) -> Iterator[bytes]:
        yield b'{"partial":'
        raise self.error

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b'{"partial":'
        raise self.error


class Chunks(httpx.SyncByteStream, httpx.AsyncByteStream):
    def __init__(self, *chunks: bytes) -> None:
        self.chunks = chunks
        self.closed = False

    def __iter__(self) -> Iterator[bytes]:
        yield from self.chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            yield chunk

    def close(self) -> None:
        self.closed = True

    async def aclose(self) -> None:
        self.closed = True


@dataclass
class Result:
    """What a scenario sent, how it ended and how long it waited."""

    requests: list[tuple[str, str, bytes, Any]]
    outcome: tuple[Any, ...]
    sleeps: list[float] = field(default_factory=list)


def summary(request: httpx.Request) -> tuple[str, str, bytes, Any]:
    body = request.content
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        # The boundary is random: compare the parts without it.
        boundary = request.headers["content-type"].split("boundary=")[1].encode()
        body = body.replace(boundary, b"BOUNDARY")
    headers = sorted(
        (name, value)
        for name, value in request.headers.multi_items()
        if not (name == "content-type" and value.startswith("multipart/"))
    )
    return request.method, str(request.url), body, (headers, request.extensions.get("timeout"))


def outcome_of(value: Any) -> tuple[Any, ...]:
    return ("ok", value.model_dump() if isinstance(value, BaseModel) else value)


def failure_of(error: Exception) -> tuple[Any, ...]:
    return ("error", type(error), str(error))


Handler = Callable[[httpx.Request], httpx.Response]


def run_sync(
    monkeypatch: pytest.MonkeyPatch,
    handler: Handler,
    run: Callable[[Any], Any],
    *,
    max_retries: int = 0,
    clock: Clock | None = None,
) -> Result:
    seen: list[httpx.Request] = []
    client = http_client()
    client._transport = httpx.MockTransport(lambda request: (seen.append(request), handler(request))[1])
    clock = clock or Clock()
    with monkeypatch.context() as context:
        context.setattr(SharedHttpClient, "get", lambda _: client)
        use_clock(context, clock)
        random.seed(0)  # the same backoff jitter for both clients
        api = BaseClient(SimpleNamespace(max_retries=max_retries), None, server_url=SERVER, api_key=KEY)
        try:
            outcome = outcome_of(run(api))
        except Exception as error:
            outcome = failure_of(error)
    return Result([summary(request) for request in seen], outcome, clock.sleeps)


async def run_async(
    monkeypatch: pytest.MonkeyPatch,
    handler: Handler,
    run: Callable[[Any], Any],
    *,
    max_retries: int = 0,
    clock: Clock | None = None,
) -> Result:
    seen: list[httpx.Request] = []
    client = async_http_client()
    client._transport = httpx.MockTransport(lambda request: (seen.append(request), handler(request))[1])
    clock = clock or Clock()
    with monkeypatch.context() as context:
        context.setattr(AsyncSharedHttpClient, "get", lambda _: client)
        use_clock(context, clock)
        random.seed(0)  # the same backoff jitter for both clients
        api = AsyncBaseClient(SimpleNamespace(max_retries=max_retries), None, server_url=SERVER, api_key=KEY)
        try:
            outcome = outcome_of(await run(api))
        except Exception as error:
            outcome = failure_of(error)
    await client.aclose()
    return Result([summary(request) for request in seen], outcome, clock.sleeps)


async def same(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[], Handler],
    run: Callable[[Any], Any],
    *,
    max_retries: int = 0,
    clock: Callable[[], Clock] = Clock,
) -> Result:
    """Run a scenario through both clients (with a fresh handler each) and require the same result."""
    expected = run_sync(monkeypatch, handler(), run, max_retries=max_retries, clock=clock())
    actual = await run_async(monkeypatch, handler(), run, max_retries=max_retries, clock=clock())
    assert actual == expected
    return expected


def sequence(*answers: httpx.Response | Exception | Callable[[], httpx.Response]) -> Callable[[], Handler]:
    """A handler factory answering each request with the next answer; the last one repeats."""

    def factory() -> Handler:
        count = 0

        def handle(request: httpx.Request) -> httpx.Response:
            nonlocal count
            answer = answers[min(count, len(answers) - 1)]
            count += 1
            if isinstance(answer, Exception):
                raise answer
            return answer() if callable(answer) else answer

        return handle

    return factory


def endpoint(method: str = "GET", path: str = "resource") -> NotteEndpoint[BaseModel]:
    return NotteEndpoint(path=path, response=BaseModel, method=method)  # pyright: ignore[reportArgumentType]


class Payload(BaseModel):
    value: str


class Empty(BaseModel):
    pass


def ok(payload: Any = None) -> Callable[[], httpx.Response]:
    return lambda: httpx.Response(200, json={"ok": True} if payload is None else payload)


def status(code: int, retry_after: str | None = None) -> Callable[[], httpx.Response]:
    headers = {} if retry_after is None else {"Retry-After": retry_after}
    return lambda: httpx.Response(code, json={"message": "unavailable", "status": code}, headers=headers)


# ---------------------------------------------------------------------------
# Retries and deadlines


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "POST", "PATCH", "DELETE"])
@pytest.mark.parametrize("code", [500, 502, 503, 504, 529, 429, 404])
@pytest.mark.parametrize("max_retries", [0, 2])
async def test_status_retries(monkeypatch: pytest.MonkeyPatch, method: str, code: int, max_retries: int) -> None:
    result = await same(
        monkeypatch,
        sequence(status(code), status(code), ok()),
        lambda api: api._request(endpoint(method)),
        max_retries=max_retries,
    )
    assert len(result.requests) in (1, 2, 3)


@pytest.mark.asyncio
@pytest.mark.parametrize("header", ["0", "4", "20", "21", "Wed, 14 Oct 2026 12:00:04 GMT", "invalid"])
async def test_retry_after(monkeypatch: pytest.MonkeyPatch, header: str) -> None:
    _ = await same(
        monkeypatch, sequence(status(503, header), ok()), lambda api: api._request(endpoint("POST")), max_retries=3
    )


@pytest.mark.asyncio
async def test_retries_use_the_remaining_time(monkeypatch: pytest.MonkeyPatch) -> None:
    result = await same(
        monkeypatch,
        sequence(status(503, "2"), ok()),
        lambda api: api._request(endpoint("POST"), timeout=10),
        max_retries=3,
    )
    assert [request[3][1]["read"] for request in result.requests] == [10, 8]


@pytest.mark.asyncio
@pytest.mark.parametrize("first", [httpx.ConnectError("refused"), status(503, "2")])
async def test_retry_deadline_is_a_requests_timeout(monkeypatch: pytest.MonkeyPatch, first: Any) -> None:
    # The backoff sleep overshoots the request's 4 s budget.
    result = await same(
        monkeypatch,
        sequence(first),
        lambda api: api._request(endpoint("POST"), timeout=4),
        max_retries=5,
        clock=lambda: Clock(step=10),
    )
    assert result.outcome == ("error", NotteRequestTimeoutError, "SDK request retry deadline exceeded")
    assert issubclass(result.outcome[1], requests.Timeout)
    assert len(result.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize(
    "error,cause",
    [
        (httpx.ConnectError("refused"), ConnectionRefusedError(61, "refused")),
        (httpx.ConnectError("dns"), socket.gaierror(8, "nodename")),
        (httpx.ConnectError("reset"), ConnectionResetError(54, "reset")),
        (httpx.ConnectError("cert"), ssl.SSLCertVerificationError("bad cert")),
        (httpx.ConnectTimeout("connect"), None),
        (httpx.PoolTimeout("pool"), None),
        (httpx.ReadTimeout("read"), None),
        (httpx.WriteTimeout("write"), None),
        (httpx.ReadError("reset"), ConnectionResetError(54, "reset")),
        (httpx.WriteError("pipe"), BrokenPipeError(32, "pipe")),
        (httpx.RemoteProtocolError("Server disconnected"), None),
        (httpx.ProxyError("proxy"), None),
        (httpx.UnsupportedProtocol("ftp"), None),
    ],
)
async def test_transport_errors(
    monkeypatch: pytest.MonkeyPatch, method: str, error: Exception, cause: BaseException | None
) -> None:
    if cause is not None:
        inner = httpcore.ConnectError(str(cause))
        inner.__context__ = cause
        inner.__suppress_context__ = True
        error.__cause__ = inner
    _ = await same(monkeypatch, sequence(error, ok()), lambda api: api._request(endpoint(method)), max_retries=2)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize(
    "error",
    [
        httpx.RemoteProtocolError("peer closed connection"),
        httpx.ReadTimeout("timed out"),
        httpx.ReadError("reset"),
        httpx.DecodingError("gzip"),
    ],
)
async def test_body_errors(monkeypatch: pytest.MonkeyPatch, method: str, error: Exception) -> None:
    _ = await same(
        monkeypatch,
        sequence(lambda: httpx.Response(200, stream=Raising(error)), ok()),
        lambda api: api._request(endpoint(method)),
        max_retries=3,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("offset", [0, 7])
async def test_uploads_are_replayed_from_their_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, offset: int
) -> None:
    path = tmp_path / "upload.txt"
    _ = path.write_text("upload content")
    upload = endpoint("POST").with_request(Payload(value="field"))
    result = await same(
        monkeypatch,
        sequence(status(503, "0"), ok()),
        lambda api: api._request_upload(upload, {"file": str(path), "named": ("other.txt", str(path))}),
        max_retries=1,
    )
    assert len(result.requests) == 2
    assert result.requests[0][2] == result.requests[1][2]
    assert b"upload content" in result.requests[0][2]


# ---------------------------------------------------------------------------
# Responses and errors


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "answer",
    [
        lambda: httpx.Response(200, content=b"<html>"),
        lambda: httpx.Response(200, json={"detail": "inline error"}),
        lambda: httpx.Response(204),
        lambda: httpx.Response(200, content=b""),
        lambda: httpx.Response(200, json=[1, 2]),
        lambda: httpx.Response(404, json={"detail": "missing"}),
        lambda: httpx.Response(502, text="Bad gateway"),
        lambda: httpx.Response(500, json={"message": "boom"}, headers={"x-error-class": "NotteApiExecutionError"}),
        lambda: httpx.Response(422, json={"message": "Extra inputs are not permitted"}),
    ],
)
async def test_responses(monkeypatch: pytest.MonkeyPatch, answer: Callable[[], httpx.Response]) -> None:
    for run in (
        lambda api: api._request(endpoint()),
        lambda api: api.request(endpoint()),
        lambda api: api.request_list(endpoint()),
        lambda api: api._request(endpoint(), check_response_detail=False),
        lambda api: api._request_bytes(endpoint()),
    ):
        _ = await same(monkeypatch, sequence(answer), run)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "body"),
    [
        *(("request_list", body) for body in [None, 3, True, "text", {"page": 1}, {"items": 3}]),
        *(("request", body) for body in [None, 3, True, "text", [1, 2]]),
    ],
)
async def test_unexpected_json_shape_is_an_api_error(monkeypatch: pytest.MonkeyPatch, method: str, body: Any) -> None:
    # A 200 whose JSON is not the object or list the method expects carries the response's status and body.
    content = json.dumps(body).encode()
    answer = sequence(lambda: httpx.Response(200, content=content, headers={"content-type": "application/json"}))
    result = await same(monkeypatch, answer, lambda api: getattr(api, method)(endpoint()))
    assert result.outcome[:2] == ("error", NotteAPIError)
    assert f"failed with status code 200: {body}" in result.outcome[2]


@pytest.mark.asyncio
async def test_request_body_query_and_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTTE_DB_PREVIEW_BRANCH", "preview-test")
    monkeypatch.setenv("NOTTE_AUTH_CAPABILITY", "capability")
    request = NotteEndpoint(
        path="action", method="PATCH", request=Payload(value="body"), params=Payload(value="query"), response=Payload
    )
    result = await same(
        monkeypatch, sequence(ok({"value": "x"})), lambda api: api.request(request, {"x-extra": "1"}, 7)
    )
    assert result.outcome == ("ok", {"value": "x"})


@pytest.mark.asyncio
async def test_malformed_server_url_is_an_sdk_exception() -> None:
    client = AsyncBaseClient(SimpleNamespace(max_retries=0), None, server_url="http://localhost:bad", api_key=KEY)
    with pytest.raises(requests.RequestException) as error:
        _ = await client._request(endpoint())
    assert isinstance(error.value, NotteInvalidURLError)
    await client._own_http.aclose()


@pytest.mark.asyncio
async def test_real_connection_refused_is_retried_for_every_method(monkeypatch: pytest.MonkeyPatch) -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.close()
    clock = Clock()
    use_clock(monkeypatch, clock)
    for client in (
        BaseClient(SimpleNamespace(max_retries=2), None, server_url=f"http://127.0.0.1:{port}", api_key=KEY),
        AsyncBaseClient(SimpleNamespace(max_retries=2), None, server_url=f"http://127.0.0.1:{port}", api_key=KEY),
    ):
        clock.sleeps.clear()
        with pytest.raises(NotteConnectionError):
            result = client._request(endpoint("POST"), timeout=5)
            if asyncio.iscoroutine(result):
                _ = await result
        assert len(clock.sleeps) == 2
        if isinstance(client, AsyncBaseClient):
            await client._own_http.aclose()


@pytest.mark.asyncio
async def test_root_cause_ignores_an_error_the_caller_was_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        raise ssl.SSLError("unrelated")
    except ssl.SSLError:
        result = await same(monkeypatch, sequence(httpx.ReadError("reset")), lambda api: api._request(endpoint()))
    assert result.outcome[1] is NotteConnectionError


# ---------------------------------------------------------------------------
# Redirects and cookies


@pytest.mark.asyncio
@pytest.mark.parametrize("hops", [30, 31])
async def test_redirects_are_capped_at_requests_limit(monkeypatch: pytest.MonkeyPatch, hops: int) -> None:
    def factory() -> Handler:
        def handle(request: httpx.Request) -> httpx.Response:
            step = int(request.url.params.get("step", "0"))
            if step < hops:
                return httpx.Response(302, headers={"location": f"{SERVER}/resource?step={step + 1}"})
            return httpx.Response(200, json={"step": step})

        return handle

    result = await same(monkeypatch, factory, lambda api: api._request(endpoint()))
    assert len(result.requests) == 31


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("target", [f"{SERVER}/moved", "/moved", "https://other.example.test/moved"])
async def test_redirect_methods_and_authorization(monkeypatch: pytest.MonkeyPatch, code: int, target: str) -> None:
    def factory() -> Handler:
        def handle(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/resource":
                return httpx.Response(code, headers={"location": target, "set-cookie": "hop=1; Path=/"})
            return httpx.Response(200, json={"cookie": request.headers.get("cookie")})

        return handle

    run = endpoint("POST").with_request(Payload(value="x"))
    # Two calls: a cookie set during the first call's redirect is not sent on the second.
    result = await same(monkeypatch, factory, lambda api: api._request(run))
    assert len(result.requests) == 2


@pytest.mark.asyncio
async def test_cookies_are_not_kept_between_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    client = async_http_client()
    client._transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, json={"cookie": request.headers.get("cookie")}, headers={"set-cookie": "a=1"}
        )
    )
    monkeypatch.setattr(AsyncSharedHttpClient, "get", lambda _: client)
    api = AsyncBaseClient(SimpleNamespace(max_retries=0), None, server_url=SERVER, api_key=KEY)
    assert await api._request(endpoint()) == {"cookie": None}
    assert await api._request(endpoint()) == {"cookie": None}
    assert len(client.cookies) == 0
    with pytest.raises(TypeError):
        client.cookies = {"a": "1"}
    await client.aclose()


# ---------------------------------------------------------------------------
# Sent once: function runs and streamed bodies


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [200, 503])
async def test_requests_sent_once(monkeypatch: pytest.MonkeyPatch, code: int) -> None:
    run = endpoint("POST").with_request(Payload(value="x"))
    answer = sequence(lambda: httpx.Response(code, json={"detail": "busy"} if code != 200 else {"ok": 1}))
    once = await same(
        monkeypatch, answer, lambda api: api._request_once(run, headers={"x-run": "1"}, timeout=5), max_retries=3
    )
    assert len(once.requests) == 1

    def lines_sync(api: BaseClient) -> list[str]:
        with api._stream_lines(run, headers={"x-run": "1"}, timeout=5) as lines:
            return list(lines)

    async def lines_async(api: AsyncBaseClient) -> list[str]:
        async with api._stream_lines(run, headers={"x-run": "1"}, timeout=5) as lines:
            return [line async for line in lines]

    expected = run_sync(monkeypatch, answer(), lines_sync, max_retries=3)
    actual = await run_async(monkeypatch, answer(), lines_async, max_retries=3)
    assert actual == expected
    assert len(actual.requests) == 1
    if code == 503:
        assert actual.outcome[1] is NotteAPIError


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "chunks",
    [
        [b'data: {"type": "log"}\n\nda', b'ta: {"type": "result"}\n'],
        [b"a\r", b"\nb", b"", b"c\n\n", b"tail"],
        [b"\n", b"\r\n", b"x"],
        [],
    ],
)
async def test_streamed_lines_split_like_sync(chunks: list[bytes]) -> None:
    sync_response = httpx.Response(200, stream=Chunks(*chunks))
    async_response = httpx.Response(200, stream=Chunks(*chunks))
    assert [line async for line in aiter_lines(async_response)] == list(iter_lines(sync_response))


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [200, 403])
async def test_streamed_bytes(monkeypatch: pytest.MonkeyPatch, code: int) -> None:
    answer = sequence(lambda: httpx.Response(code, stream=Chunks(b"ab", b"", b"cd")))

    def read_sync(api: BaseClient) -> bytes:
        with api._stream_bytes(endpoint()) as chunks:
            return b"|".join(chunks)

    async def read_async(api: AsyncBaseClient) -> bytes:
        async with api._stream_bytes(endpoint()) as chunks:
            return b"|".join([chunk async for chunk in chunks])

    expected = run_sync(monkeypatch, answer(), read_sync)
    actual = await run_async(monkeypatch, answer(), read_async)
    assert actual == expected


@pytest.mark.asyncio
async def test_streamed_responses_are_closed() -> None:
    body = Chunks(b"x")
    async with async_http_client() as client:
        client._transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=body))
        with pytest.raises(RuntimeError):
            async with astream(client, client.build_request("GET", SERVER)):
                raise RuntimeError("caller failure")
        assert body.closed
        body.closed = False
        assert (await asend(client, client.build_request("GET", SERVER))).content == b"x"
        assert body.closed


# ---------------------------------------------------------------------------
# TLS handshake recovery, against a real TLS server


@pytest.fixture
def fast_handshakes(monkeypatch: pytest.MonkeyPatch) -> Clock:
    clock = Clock()
    use_clock(monkeypatch, clock)
    monkeypatch.setattr("notte_sdk._transport.random.uniform", lambda *_: 0.05)
    return clock


def trusted_async(monkeypatch: pytest.MonkeyPatch, ca: str) -> httpx.AsyncClient:
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", ca)
    return async_http_client()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("reset", [False, True])
async def test_handshake_recovery_sends_one_request(
    certificate: Any,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    fast_handshakes: Clock,
    method: str,
    reset: bool,
) -> None:
    with tls_server(certificate, failures=2, reset=reset) as (url, ca, state):
        async with trusted_async(monkeypatch, ca) as client:
            result = await asend(client, client.build_request(method, url, content=b"payload", timeout=2))
        assert result.status_code == 200
        assert state["connections"] == 3
        assert [body for _, body in state["requests"]] == [b"payload"]
        assert fast_handshakes.sleeps == [0.3, 0.8]


@pytest.mark.asyncio
@pytest.mark.parametrize("reset", [False, True])
async def test_persistent_handshake_failure_raises_the_sync_exception(
    certificate: Any,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    fast_handshakes: Clock,
    reset: bool,
) -> None:
    raised: list[type[Exception]] = []
    with tls_server(certificate, failures=10, reset=reset) as (url, ca, state):
        monkeypatch.setenv("REQUESTS_CA_BUNDLE", ca)
        with http_client() as client, pytest.raises(NotteConnectionError) as error:
            _ = send(client, client.build_request("POST", url, content=b"payload", timeout=2))
        raised.append(type(error.value))
        async with async_http_client() as aclient:
            with pytest.raises(NotteConnectionError) as aerror:
                _ = await asend(aclient, aclient.build_request("POST", url, content=b"payload", timeout=2))
        raised.append(type(aerror.value))
        assert state["connections"] == 6
        assert state["requests"] == []
    assert raised == [NotteConnectionError if reset else NotteSSLError] * 2


@pytest.mark.asyncio
@pytest.mark.parametrize("response", ["drop", "timeout", "503"])
async def test_post_is_never_replayed_after_transmission(
    certificate: Any,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    fast_handshakes: Clock,
    response: str,
) -> None:
    with tls_server(certificate, response=response) as (url, ca, state):
        async with trusted_async(monkeypatch, ca) as client:
            request = client.build_request("POST", url, content=b"action", timeout=0.2)
            if response == "503":
                assert (await asend(client, request)).status_code == 503
            else:
                with pytest.raises(requests.exceptions.RequestException) as error:
                    _ = await asend(client, request)
                assert isinstance(error.value, NotteRequestError)
        assert state["connections"] == 1
        assert len(state["requests"]) == 1


@pytest.mark.asyncio
async def test_certificate_rejection_is_not_retried(certificate: Any) -> None:  # noqa: F811
    with tls_server(certificate) as (url, _, state):
        async with async_http_client() as client:
            with pytest.raises(requests.exceptions.SSLError) as error:
                _ = await asend(client, client.build_request("GET", url, timeout=2))
        assert isinstance(error.value, NotteSSLError)
        assert state["connections"] == 1
        assert state["requests"] == []


@pytest.mark.asyncio
async def test_explicit_redirect_after_recovery(
    certificate: Any,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    fast_handshakes: Clock,
) -> None:
    with tls_server(certificate, failures=1, response="redirect") as (url, ca, state):
        async with trusted_async(monkeypatch, ca) as client:
            result = await asend(client, client.build_request("POST", url, content=b"body", timeout=2))
        assert result.status_code == 200
        assert len(result.history) == 1
        assert state["connections"] == 3
        assert state["requests"][1][0].startswith(b"POST /next ")
        assert all(body == b"body" for _, body in state["requests"])


@pytest.mark.asyncio
async def test_handshake_backend_is_local_and_proxy_pool_is_unmodified(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.test:3128")
    async with async_http_client() as client, httpx.AsyncClient() as normal:
        assert isinstance(client._transport._pool._network_backend, _AsyncHandshakeBackend)
        assert not isinstance(normal._transport._pool._network_backend, _AsyncHandshakeBackend)
        proxy = client._transport_for_url(httpx.URL("https://example.test"))
        assert proxy is not client._transport
        assert isinstance(proxy._pool, httpcore.AsyncHTTPProxy)
        assert not isinstance(proxy._pool._network_backend, _AsyncHandshakeBackend)


class AsyncFakeStream(httpcore.AsyncNetworkStream):
    def __init__(self, error: Exception | None = None) -> None:
        self.sync = FakeStream(error)

    async def aclose(self) -> None:
        self.sync.close()

    async def start_tls(self, ssl_context: Any, server_hostname: Any = None, timeout: Any = None) -> Any:
        return self.sync.start_tls(ssl_context, server_hostname, timeout) and self


def connector(streams: list[AsyncFakeStream]) -> tuple[Mock, Callable[[], Any]]:
    calls = Mock()

    async def connect() -> AsyncFakeStream:
        calls()
        return streams[calls.call_count - 1]

    return calls, connect


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        handshake_failure(ssl.SSLError("unsupported protocol")),
        handshake_failure(ssl.SSLCertVerificationError("bad cert")),
        handshake_failure(ConnectionRefusedError("refused")),
        httpcore.ConnectTimeout("handshake timed out"),
    ],
)
async def test_other_handshake_errors_are_not_retried(error: Exception) -> None:
    streams = [AsyncFakeStream(error)]
    calls, connect = connector(streams)
    stream = _AsyncHandshakeStream(connect, "example.test", await connect())
    with pytest.raises(type(error)) as caught:
        _ = await stream.start_tls(ssl.create_default_context(), "example.test", 1.0)
    assert caught.value is error
    assert calls.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cause",
    [
        ssl.SSLEOFError("sensitive exception text"),
        ConnectionResetError("sensitive exception text"),
        # anyio's reports of the same failures under the async transport.
        __import__("anyio").EndOfStream(),
    ],
)
async def test_exhaustion_preserves_error_closes_sockets_and_logs_no_path(
    fast_handshakes: Clock, cause: BaseException
) -> None:
    error = handshake_failure(cause)
    streams = [AsyncFakeStream(error) for _ in range(3)]
    calls, connect = connector(streams)
    with patch("notte_sdk._transport.logger.warning") as log:
        stream = _AsyncHandshakeStream(connect, "example.test", await connect())
        with pytest.raises(httpcore.ConnectError) as caught:
            _ = await stream.start_tls(ssl.create_default_context(), "example.test", 1.5)
    assert caught.value is error
    assert calls.call_count == 3
    assert all(item.sync.closed for item in streams)
    assert [item.sync.handshakes for item in streams] == [[1.5], [1.5], [1.5]]
    assert fast_handshakes.sleeps == [0.3, 0.8]
    assert log.call_count == 3
    assert "sensitive" not in str(log.call_args_list)


@pytest.mark.asyncio
async def test_each_reconnect_gets_the_callers_timeout(fast_handshakes: Clock) -> None:
    error = handshake_failure(ConnectionResetError("reset"))
    streams = [AsyncFakeStream(error) for _ in range(3)]
    timeouts: list[float | None] = []

    async def connect_tcp(
        host: str, port: int, timeout: float | None = None, local_address: Any = None, socket_options: Any = None
    ) -> AsyncFakeStream:
        timeouts.append(timeout)
        return streams[len(timeouts) - 1]

    backend = _AsyncHandshakeBackend()
    backend._backend = SimpleNamespace(connect_tcp=connect_tcp)
    stream = await backend.connect_tcp("example.test", 443, timeout=1.5)
    with pytest.raises(httpcore.ConnectError):
        _ = await stream.start_tls(ssl.create_default_context(), "example.test", 1.5)
    assert timeouts == [1.5, 1.5, 1.5]


@pytest.mark.asyncio
async def test_sdk_preserves_headers_query_and_body_during_recovery(
    certificate: Any,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    fast_handshakes: Clock,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("NOTTE_DB_PREVIEW_BRANCH", "preview-test")
    file = tmp_path / "upload.txt"
    _ = file.write_text("upload-data")
    with tls_server(certificate, failures=1) as (url, ca, state):
        monkeypatch.setenv("REQUESTS_CA_BUNDLE", ca)
        client = AsyncBaseClient(SimpleNamespace(max_retries=0), None, server_url=url, api_key="test-token")
        request = NotteEndpoint(
            path="action", method="POST", request=Payload(value="test"), params=Payload(value="query"), response=Payload
        )
        assert await client._request(request, timeout=2) == {}
        upload = request.model_copy(update={"response": Empty})
        assert await client._request_upload(upload, {"file": str(file)}) == Empty()
        await client._own_http.aclose()
    assert state["connections"] == 3
    (json_head, json_body), (form_head, form_body) = state["requests"]
    assert b"POST /action?value=query HTTP/1.1" in json_head
    assert b"Authorization: Bearer test-token" in json_head
    assert b"x-db-preview: preview-test" in json_head
    assert json_body == b'{"value":"test"}'
    assert b"multipart/form-data" in form_head
    assert b"upload-data" in form_body
    assert b'name="value"' in form_body


# ---------------------------------------------------------------------------
# Lifecycle


def notte(url: str = SERVER) -> AsyncNotteClient:
    return AsyncNotteClient(api_key=KEY, server_url=url)


@pytest.mark.asyncio
async def test_one_lazily_opened_pool_per_client(keep_alive_server: tuple[str, dict[str, int]]) -> None:  # noqa: F811
    url, state = keep_alive_server
    client = notte(url)
    assert client._http._client is None  # nothing opens before the first request
    assert client.sessions.http is client.personas.http is client.functions.http
    for resource in (client.sessions, client.personas, client.vaults, client.files, client.profiles):
        _ = await resource._request(endpoint())
    assert state["connections"] == 1
    pooled = client.sessions.http
    await client.aclose()
    assert pooled.is_closed
    assert client._http._client is None
    await client.aclose()  # closing twice is harmless
    # A closed client reconnects on its next request.
    _ = await client.sessions._request(endpoint())
    assert client.sessions.http is not pooled
    assert state["connections"] == 2
    async with client as same_client:
        assert same_client is client
        reopened = client.sessions.http
        _ = await client.sessions._request(endpoint())
    assert reopened.is_closed


@pytest.mark.asyncio
async def test_unclosed_client_warns_when_collected() -> None:
    client = notte()
    _ = client.sessions.http
    with pytest.warns(ResourceWarning, match="aclose"):
        del client
        _ = gc.collect()


@pytest.mark.asyncio
async def test_closed_or_unused_client_does_not_warn() -> None:
    closed = notte()
    _ = closed.sessions.http
    await closed.aclose()
    unused = notte()
    with warnings.catch_warnings():
        warnings.simplefilter("error", ResourceWarning)
        del closed, unused
        _ = gc.collect()


@pytest.fixture
def other_loop() -> Iterator[asyncio.AbstractEventLoop]:
    """An event loop running in another thread."""
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    try:
        yield loop
    finally:
        _ = loop.call_soon_threadsafe(loop.stop)
        thread.join(5)
        loop.close()


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_another_open_loop_fails_clearly(
    keep_alive_server: tuple[str, dict[str, int]],  # noqa: F811
    other_loop: asyncio.AbstractEventLoop,
) -> None:
    url, _ = keep_alive_server
    client = notte(url)

    def in_other_loop(coroutine: Any) -> Any:
        return asyncio.run_coroutine_threadsafe(coroutine, other_loop).result(5)

    assert in_other_loop(client.sessions._request(endpoint())) == {}

    async def pool() -> httpx.AsyncClient:
        return client.sessions.http

    pooled = in_other_loop(pool())
    with pytest.raises(RuntimeError, match="another event loop"):
        _ = await client.sessions._request(endpoint())
    with pytest.raises(RuntimeError, match="another event loop"):
        await client.aclose()
    assert not pooled.is_closed
    # Its own loop closes it; then any loop can use the client.
    in_other_loop(client.aclose())
    assert pooled.is_closed
    assert await client.sessions._request(endpoint()) == {}
    await client.aclose()


@pytest.mark.timeout(10)
def test_loops_in_two_threads_cannot_both_take_the_pool() -> None:
    shared = AsyncSharedHttpClient()
    created: list[Mock] = []
    both_waiting = threading.Barrier(2)
    # Both loops stay open until both have checked ownership: a closed owner loop is replaced.
    both_checked = threading.Barrier(2)

    def slow_client() -> Mock:
        # SSL setup is slow enough for a second thread to pass an unlocked ownership check.
        time.sleep(0.2)
        client = Mock(spec=httpx.AsyncClient)
        created.append(client)
        return client

    outcomes: list[object] = []

    def first_request() -> None:
        async def get() -> object:
            _ = both_waiting.wait(5)
            try:
                return shared.get()
            except RuntimeError as error:
                return error
            finally:
                _ = both_checked.wait(5)

        outcomes.append(asyncio.run(get()))

    with patch("notte_sdk._transport.async_http_client", side_effect=slow_client):
        threads = [threading.Thread(target=first_request) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
    # One loop owns the only pool; the other gets the other-loop error, not a second pool.
    assert len(created) == 1
    assert sorted(type(outcome).__name__ for outcome in outcomes) == ["Mock", "RuntimeError"]
    assert shared._client is created[0]  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_a_closed_loops_connections_are_replaced(keep_alive_server: tuple[str, dict[str, int]]) -> None:  # noqa: F811
    url, state = keep_alive_server
    client = notte(url)

    def use_then_close_loop() -> None:
        loop = asyncio.new_event_loop()
        try:
            assert loop.run_until_complete(client.sessions._request(endpoint())) == {}
        finally:
            loop.close()

    # Independent loops cannot run on the test's already-running loop thread.
    await asyncio.to_thread(use_then_close_loop)
    stale = client._http._client
    with warnings.catch_warnings():
        # The stale loop's sockets were never closed; collecting them may warn.
        warnings.simplefilter("ignore", ResourceWarning)
        assert await client.sessions._request(endpoint()) == {}
    assert client._http._client is not stale
    assert state["connections"] == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_forked_process_gets_its_own_connections() -> None:
    client = notte()
    parent = client.sessions.http
    with patch("notte_sdk._transport.os.getpid", return_value=-1):
        child = client.sessions.http
        assert child is not parent
        await client.aclose()
        assert child.is_closed
    # The child never closes the parent's connections.
    assert not parent.is_closed
    await parent.aclose()


@pytest.mark.skipif(not hasattr(os, "fork"), reason="os.fork is POSIX only")
def test_forked_child_opens_new_connections_and_leaves_the_parents_open(
    keep_alive_server: tuple[str, dict[str, int]],  # noqa: F811
) -> None:
    url, state = keep_alive_server
    client = notte(url)
    loop = asyncio.new_event_loop()
    try:
        assert loop.run_until_complete(client.sessions._request(endpoint())) == {}
        parent = client._http._client
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)  # fork() in a multi-threaded process
            pid = os.fork()
        if pid == 0:  # child: a new event loop, as after any fork
            code = 1
            try:
                _ = signal.alarm(5)  # a hang ends the child with SIGALRM
                # A forked child of a threaded process must not resolve names or start threads on
                # macOS, so the child's new connections are answered in memory.
                fresh = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={})))
                with patch("notte_sdk._transport.async_http_client", return_value=fresh):
                    child_loop = asyncio.new_event_loop()
                    assert child_loop.run_until_complete(client.sessions._request(endpoint())) == {}
                    assert client._http._client is fresh
                    child_loop.run_until_complete(client.aclose())
                    assert fresh.is_closed
                code = 0
            finally:
                os._exit(code)
        _, status = os.waitpid(pid, 0)
        assert os.waitstatus_to_exitcode(status) == 0
        # The child opened its own client and closed only that one: the parent's pool is untouched.
        assert state["connections"] == 1
        assert client._http._client is parent
        assert parent is not None and not parent.is_closed
        assert loop.run_until_complete(client.sessions._request(endpoint())) == {}
        assert state["connections"] == 1
        loop.run_until_complete(client.aclose())
    finally:
        loop.close()


def test_sync_client_is_unaffected_by_an_async_one() -> None:
    sync, async_ = NotteClient(api_key=KEY), notte()
    assert isinstance(sync._http, SharedHttpClient)
    assert isinstance(async_._http, AsyncSharedHttpClient)
    assert isinstance(sync.sessions.http, httpx.Client)
