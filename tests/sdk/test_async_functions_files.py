"""`AsyncNotteClient` functions, run payloads and files: the sync behavior, as coroutines.

Each flow is written once and runs through both clients with `exchange_sync` / `exchange_async`,
which also route the separate object-storage clients. Both must send the same requests (API and
storage, with the same headers) and return the same result or raise the same error.
"""

import asyncio
import base64
import hashlib
import inspect
import io
import json
import threading
import typing
from collections.abc import Awaitable, Callable, Coroutine
from pathlib import Path
from typing import Any

import httpx
import pytest
from notte_core._sync import run_sync
from notte_core.logging import logger
from notte_sdk import AsyncNotteClient, NotteClient
from notte_sdk._transport import AsyncSharedHttpClient, async_http_client
from notte_sdk._v1_aliases import _RENAMED_ATTRS, _RENAMED_METHODS
from notte_sdk.endpoints import base as base_module
from notte_sdk.endpoints import files as files_module
from notte_sdk.endpoints import run_payloads
from notte_sdk.endpoints.files import AsyncRemoteFileStorage, RemoteFileStorage
from notte_sdk.endpoints.functions import AsyncNotteFunction, NotteFunction

from tests.sdk.test_async_resources import (
    FUNCTION,
    KEY,
    RUN,
    STAMP,
    Exchange,
    exchange_async,
    exchange_sync,
    mocked,
)
from tests.sdk.test_generated_endpoints import SERVER

STORAGE_HOST = "storage.test"
LINK = {**FUNCTION, "url": f"https://{STORAGE_HOST}/code.py"}
CODE = "def run():\n    return 1\n"
SESSION_STATUS = dict(
    session_id="s-9",
    idle_timeout_minutes=3,
    created_at=STAMP,
    last_accessed_at=STAMP,
    status="active",
    viewer_url="https://console.test/viewer?jwt=x",
)
UPDATED_RUN = {"function_id": "f-1", "function_run_id": "r-1", "updated_at": STAMP}
Routes = dict[tuple[str, str], Any]


def checksum(raw: bytes) -> str:
    return base64.b64encode(hashlib.sha256(raw).digest()).decode()


def sse(*events: dict[str, Any]) -> bytes:
    return b"\n\n".join(("data: " + json.dumps(event)).encode() for event in events)


def file_entry(file_id: str, filename: str = "input.txt", source: str = "user_upload") -> dict[str, Any]:
    return dict(
        id=file_id,
        session_id="s-1",
        filename=filename,
        mime_type="text/plain",
        size=5,
        checksum="a" * 64,
        created_at=STAMP,
        expires_at=STAMP,
        source=source,
    )


class Api:
    """The API and object storage of one flow, answering by method and path (`storage` for the
    storage host). A route is a JSON payload, raw bytes, a response, or a function of the request."""

    def __init__(self, routes: Routes) -> None:
        self.routes: Routes = routes

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = "storage" if request.url.host == STORAGE_HOST else request.url.path
        route = self.routes.get((request.method, path), httpx.Response(404, json={"detail": f"no route: {path}"}))
        if callable(route):
            route = route(request)
        if isinstance(route, httpx.Response):
            # A fresh copy: each client reads (and closes) its own response.
            return httpx.Response(route.status_code, headers=route.headers, content=route.content)
        return httpx.Response(200, content=route if isinstance(route, bytes) else json.dumps(route).encode())


Flow = Callable[[Any, Callable[[Any], Awaitable[Any]]], Coroutine[Any, Any, Any]]


async def _passthrough(value: Any) -> Any:
    return value


async def _await(value: Any) -> Any:
    return await value


def _drive(coroutine: Coroutine[Any, Any, Any]) -> Any:
    """Run the sync client's flow, including its genuinely async storage interface."""
    return run_sync(coroutine)


async def same_exchange(monkeypatch: pytest.MonkeyPatch, routes: Routes, flow: Flow) -> Exchange:
    """Run `flow(client, wait)` on both clients: `wait` awaits on the async client only."""
    expected = exchange_sync(monkeypatch, Api(routes), lambda client: _drive(flow(client, _passthrough)))
    actual = await exchange_async(monkeypatch, Api(routes), lambda client: flow(client, _await))
    assert actual == expected
    assert expected.calls, f"the flow sent no request: {expected.outcome}"
    return expected


# ---------------------------------------------------------------------------
# The same public methods


def public(cls: type) -> set[str]:
    """Public members, without the deprecated 1.x aliases, which the async client does not carry over."""
    names = {name for klass in cls.__mro__ if klass is not object for name in vars(klass) if not name.startswith("_")}
    return names - set(_RENAMED_METHODS.get(cls, {})) - set(_RENAMED_ATTRS.get(cls, {}))


def hints(function: Callable[..., Any], sync: type, async_: type) -> dict[str, Any]:
    """Resolved type hints, with the sync class written as its async twin."""
    return {name: async_ if value is sync else value for name, value in typing.get_type_hints(function).items()}


# Sync methods without an async twin yet.
PENDING: dict[type, set[str]] = {NotteFunction: set(), RemoteFileStorage: set()}
# Members that are not async twins of a sync method, and why.
FUNCTION_EXCEPTIONS = {
    # Properties: they send no request, and raise until the function was awaited or used.
    "response",
    "function_id",
}
STORAGE_EXCEPTIONS = {
    # No I/O: plain members on both.
    "is_remote",
    "captures_browser_downloads",
    "set_session_id",
    "for_session",
    "session_id",
}


@pytest.mark.parametrize(
    "sync,async_,exceptions",
    [
        (NotteFunction, AsyncNotteFunction, FUNCTION_EXCEPTIONS),
        (RemoteFileStorage, AsyncRemoteFileStorage, STORAGE_EXCEPTIONS),
    ],
)
def test_stateful_classes_have_the_sync_methods_as_coroutines(sync: type, async_: type, exceptions: set[str]) -> None:
    # Async storage also implements the local browser's async storage interface.
    async_only = {"alist_uploaded_files", "alist_downloaded_files"} if sync is RemoteFileStorage else set()
    assert public(sync) - PENDING[sync] == public(async_) - async_only
    for name in public(async_) - exceptions - async_only:
        sync_method, async_method = getattr(sync, name), getattr(async_, name)
        assert not inspect.iscoroutinefunction(sync_method), name
        assert inspect.iscoroutinefunction(async_method), name
        assert inspect.signature(sync_method).parameters.keys() == inspect.signature(async_method).parameters.keys()
        assert hints(sync_method, sync, async_) == hints(async_method, sync, async_), name
    assert inspect.signature(sync.__init__).parameters.keys() == inspect.signature(async_.__init__).parameters.keys()


def test_storage_interface_is_async_on_the_async_storage() -> None:
    for name in ("get_file", "set_file", "alist_uploaded_files", "alist_downloaded_files", "instructions"):
        assert inspect.iscoroutinefunction(getattr(AsyncRemoteFileStorage, name)), name
    for name in ("is_remote", "session_id"):
        assert getattr(AsyncRemoteFileStorage, name) is getattr(RemoteFileStorage, name), name


def test_factories_build_the_async_objects() -> None:
    client = AsyncNotteClient(api_key=KEY, server_url=SERVER)
    function = client.Function("f-1")
    assert isinstance(function, AsyncNotteFunction)
    assert (function.client, function.root_client, function.function_id) == (client.functions, client, "f-1")
    with pytest.raises(ValueError, match="await"):
        _ = function.response
    storage = client.FileStorage("s-1")
    assert isinstance(storage, AsyncRemoteFileStorage)
    assert (storage.client, storage.session_id, storage.is_remote) == (client.files, "s-1", True)
    assert storage.for_session("s-1") is storage
    other = storage.for_session("s-2")
    # The class the module defines now: tests/cache reloads `notte_sdk.endpoints.files`.
    assert isinstance(other, files_module.AsyncRemoteFileStorage)
    assert (other.client, other.session_id) == (client.files, "s-2")
    with pytest.raises(ValueError, match="AsyncFileStorageClient is required"):
        _ = AsyncRemoteFileStorage("s-1")
    with pytest.raises(ValueError, match="FileStorageClient is required"):
        _ = RemoteFileStorage("s-1")
    with pytest.raises(ValueError, match="AsyncNotteClient is required"):
        _ = AsyncNotteFunction("f-1")
    with pytest.raises(ValueError, match="must end with .py"):
        _ = client.Function(path="function.txt")


# ---------------------------------------------------------------------------
# Functions: the same requests


def run_routes(stream_status: str = "closed") -> Routes:
    result = {"function_id": "f-1", "function_run_id": "r-1", "session_id": "s-9", "status": stream_status}

    def start(request: httpx.Request) -> Any:
        if not json.loads(request.content)["stream"]:
            return {**result, "result": "1"}
        return sse(
            {"type": "session_start", "message": "s-9"},
            {"type": "log", "message": "2026 | \x1b[32mINFO\x1b[0m | module | running"},
            {"type": "unknown", "message": "ignored"},
            {"type": "result", "message": json.dumps({**result, "result": {"ok": True}})},
        )

    return {
        ("POST", "/functions/"): FUNCTION,
        ("GET", "/functions/f-1"): LINK,
        ("POST", "/functions/f-1"): FUNCTION,
        ("DELETE", "/functions/f-1"): {"status": "success", "message": "deleted"},
        ("POST", "/functions/f-1/fork"): {**FUNCTION, "function_id": "f-2"},
        ("POST", "/functions/f-1/runs/create"): {**RUN, "status": "created"},
        ("POST", "/functions/f-1/runs/r-1"): start,
        ("DELETE", "/functions/f-1/runs/r-1"): UPDATED_RUN,
        ("GET", "/functions/f-1/runs/r-1"): RUN,
        ("PATCH", "/functions/f-1/runs/r-1"): UPDATED_RUN,
        ("GET", "/sessions/s-9"): SESSION_STATUS,
        ("GET", "/sessions/s-9/replay"): {"mp4_url": "https://cdn.test/r.mp4", "expires_at": STAMP},
        ("GET", "storage"): CODE.encode(),
    }


@pytest.fixture
def upload(tmp_path: Path) -> str:
    path = tmp_path / "notes.txt"
    _ = path.write_text("upload-data")
    return str(path)


@pytest.fixture
def code(tmp_path: Path) -> str:
    path = tmp_path / "function.py"
    _ = path.write_text(CODE)
    return str(path)


def resource_flows(code: str) -> dict[str, Flow]:
    async def update(c: Any, wait: Any) -> Any:
        return await wait(c.functions.update("f-1", False, path=code, version="v1"))

    async def update_restricted(c: Any, wait: Any) -> Any:
        return await wait(c.functions.update("f-1", path=code))

    async def create_run(c: Any, wait: Any) -> Any:
        return await wait(c.functions.create_run("f-1"))

    async def run_start_stream(c: Any, wait: Any) -> Any:
        return await wait(c.functions.run_start("r-1", function_id="f-1", variables={"a": 1}, runtime="extended"))

    async def run_start_once(c: Any, wait: Any) -> Any:
        return await wait(c.functions.run_start("r-1", timeout=30, workflow_id="f-1", stream=False))

    async def run_get_metadata(c: Any, wait: Any) -> Any:
        return await wait(c.functions.run_get_metadata("f-1", "r-1"))

    async def run_update_metadata(c: Any, wait: Any) -> Any:
        return await wait(c.functions.run_update_metadata("f-1", "r-1", status="closed", result={"ok": 1}))

    return {name: flow for name, flow in locals().items() if name != "code"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name",
    [
        "update",
        "update_restricted",
        "create_run",
        "run_start_stream",
        "run_start_once",
        "run_get_metadata",
        "run_update_metadata",
    ],
)
async def test_functions_resource_sends_the_same_requests(
    monkeypatch: pytest.MonkeyPatch, code: str, name: str
) -> None:
    exchange = await same_exchange(monkeypatch, run_routes(), resource_flows(code)[name])
    assert exchange.outcome[0] == "ok", exchange.outcome
    if name.startswith("update"):
        assert exchange.calls[0].files["file"][1] == CODE.encode()
        assert exchange.calls[0].params == ({"restricted": "False", "version": "v1"} if name == "update" else {})
    if name == "run_start_stream":
        start, status = exchange.calls
        assert start.headers["x-notte-api-key"] == KEY
        assert status.timeout == {"connect": 2, "read": 2, "write": 2, "pool": 2}
        assert exchange.outcome[1]["result"] == {"ok": True}
    if name == "run_start_once":
        assert exchange.calls[0].timeout["read"] == 30


def test_get_curl_and_decode_message_match() -> None:
    sync = NotteClient(api_key=KEY, server_url=SERVER).functions
    async_ = AsyncNotteClient(api_key=KEY, server_url=SERVER).functions
    assert async_.get_curl("f-1", a=1, b=[1, 2]) == sync.get_curl("f-1", a=1, b=[1, 2])
    message = "2026 | \x1b[31;1mERROR\x1b[0m | module | broken"
    assert async_.decode_message(message) == sync.decode_message(message) == "broken"


@pytest.mark.asyncio
@pytest.mark.parametrize("events", ["no_result", "bad_json", "missing_viewer"])
async def test_run_stream_edge_cases_match(monkeypatch: pytest.MonkeyPatch, events: str) -> None:
    result = {"function_id": "f-1", "function_run_id": "r-1", "session_id": None, "status": "closed", "result": 1}
    body = {
        "no_result": sse({"type": "log", "message": "only logs"}),
        "bad_json": b"data: {not json\n\nevent: ping\n\n" + sse({"type": "result", "message": json.dumps(result)}),
        "missing_viewer": sse(
            {"type": "session_start", "message": "s-9"}, {"type": "result", "message": json.dumps(result)}
        ),
    }[events]
    routes = {
        ("POST", "/functions/f-1/runs/r-1"): body,
        ("GET", "/sessions/s-9"): httpx.Response(500, json={"detail": "down"}),
    }

    async def flow(c: Any, wait: Any) -> Any:
        return await wait(c.functions.run_start("r-1", function_id="f-1"))

    exchange = await same_exchange(monkeypatch, routes, flow)
    if events == "no_result":
        assert exchange.outcome == ("error", ValueError, "Did not get any result from function run")
    else:
        assert exchange.outcome[0] == "ok"


@pytest.mark.asyncio
async def test_run_stream_logs_the_same_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    async def flow(c: Any, wait: Any) -> Any:
        return await wait(c.functions.run_start("r-1", function_id="f-1"))

    outputs: list[str] = []
    for exchange in (exchange_sync, exchange_async):
        captured = io.StringIO()
        handler = logger.add(captured, level="INFO", format="{message}")
        try:
            if exchange is exchange_sync:
                _ = exchange_sync(monkeypatch, Api(run_routes()), lambda c: _drive(flow(c, _passthrough)))
            else:
                _ = await exchange_async(monkeypatch, Api(run_routes()), lambda c: flow(c, _await))
        finally:
            logger.remove(handler)
        outputs.append(captured.getvalue())
    assert outputs[0] == outputs[1]
    assert "running" in outputs[0]
    assert "Live viewer for session available at: https://console.test/viewer?jwt=x" in outputs[0]
    assert KEY not in outputs[0]


def function_flows(code: str, tmp_path: Path) -> dict[str, Flow]:
    async def create_and_run(c: Any, wait: Any) -> Any:
        function = await wait(c.Function(path=code, name="f"))
        return await wait(function.run(url="https://example.com"))

    async def run_once_with_run_id(c: Any, wait: Any) -> Any:
        return await wait(c.Function("f-1").run(stream=False, function_run_id="r-1", input_variables={"x": 1}))

    async def replay_run_session(c: Any, wait: Any) -> Any:
        # Functions have no `replay`: replay the session the run returned.
        result = await wait(c.Function("f-1").run(stream=False))
        return await wait(c.sessions.replay(session_id=result.session_id))

    async def failed_run(c: Any, wait: Any) -> Any:
        return await wait(c.Function("f-1").run())

    async def run_rejects_version(c: Any, wait: Any) -> Any:
        return await wait(c.Function("f-1").run(version="v2"))

    async def lifecycle(c: Any, wait: Any) -> Any:
        function = c.Function("f-1")
        created = await wait(function.create_run())
        run = await wait(function.get_run("r-1"))
        stopped = await wait(function.stop_run("r-1"))
        curl = await wait(function.get_curl(a=1))
        await wait(function.update(code, restricted=False))
        forked = await wait(function.fork())
        await wait(function.delete())
        # The sync `function_id` of a fork fetches its metadata; the async one does not.
        return [created, run, stopped, curl, function.response, type(forked).__name__.removeprefix("Async")]

    async def download(c: Any, wait: Any) -> Any:
        function = c.Function("f-1")
        target = str(tmp_path / "downloaded.py")
        url = await wait(function.get_url())
        text = await wait(function.download(target))
        return [url, text, Path(target).read_text(), await wait(function.download())]

    async def download_other_version(c: Any, wait: Any) -> Any:
        return await wait(c.Function("f-1").get_url(version="v0"))

    return {name: flow for name, flow in locals().items() if name not in ("code", "tmp_path")}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name",
    [
        "create_and_run",
        "run_once_with_run_id",
        "replay_run_session",
        "failed_run",
        "run_rejects_version",
        "lifecycle",
        "download",
        "download_other_version",
    ],
)
async def test_function_objects_send_the_same_requests(
    monkeypatch: pytest.MonkeyPatch, code: str, tmp_path: Path, name: str
) -> None:
    routes = run_routes("failed" if name == "failed_run" else "closed")
    if name == "run_rejects_version":
        exchange = exchange_sync(
            monkeypatch, Api(routes), lambda c: _drive(function_flows(code, tmp_path)[name](c, _passthrough))
        )
        assert exchange.outcome[0] == "error" and not exchange.calls
        assert (
            await exchange_async(monkeypatch, Api(routes), lambda c: function_flows(code, tmp_path)[name](c, _await))
            == exchange
        )
        return
    exchange = await same_exchange(monkeypatch, routes, function_flows(code, tmp_path)[name])
    if name == "failed_run":
        assert exchange.outcome[0] == "error"
        assert exchange.outcome[1].__name__ == "FailedToRunCloudFunctionError"
    else:
        assert exchange.outcome[0] == "ok", exchange.outcome
    if name == "replay_run_session":
        assert ("GET", f"{SERVER}/sessions/s-9/replay") in [(call.method, call.url) for call in exchange.calls]
        assert exchange.outcome[1]["mp4_url"] == "https://cdn.test/r.mp4"
    if name == "download":
        storage = [call for call in exchange.calls if STORAGE_HOST in call.url]
        assert storage and all("Authorization" not in call.headers for call in storage)


@pytest.mark.asyncio
async def test_awaiting_a_function_creates_it_once(monkeypatch: pytest.MonkeyPatch, code: str) -> None:
    async def flow(c: Any, wait: Any) -> Any:
        function = c.Function(path=code)
        if wait is _passthrough:
            # Sync functions are created by the constructor; run the same requests in order.
            return [function.run(stream=False).status for _ in range(3)]
        results = await asyncio.gather(*(function.run(stream=False) for _ in range(3)))
        return [result.status for result in results]

    async_exchange = await exchange_async(monkeypatch, Api(run_routes()), lambda c: flow(c, _await))
    sync_exchange = exchange_sync(monkeypatch, Api(run_routes()), lambda c: _drive(flow(c, _passthrough)))
    assert async_exchange.outcome == sync_exchange.outcome == ("ok", ["closed"] * 3)
    paths = sorted((call.method, call.url) for call in async_exchange.calls)
    assert paths == sorted((call.method, call.url) for call in sync_exchange.calls)
    assert [path for path in paths if path == ("POST", f"{SERVER}/functions/")] == [("POST", f"{SERVER}/functions/")]


@pytest.mark.asyncio
async def test_unawaited_function_properties_explain_what_to_do(code: str) -> None:
    client = AsyncNotteClient(api_key=KEY, server_url=SERVER)
    function = client.Function(path=code)
    with pytest.raises(ValueError, match="await client.Function"):
        _ = function.function_id
    with pytest.raises(ValueError, match="await"):
        _ = function.response


# ---------------------------------------------------------------------------
# Run payloads: the same verification, the same storage requests


def upload_answer(request: httpx.Request) -> dict[str, Any]:
    """`prepare_run_payload_upload`: a reference to what the client declared."""
    declared = json.loads(request.content)
    return {
        "reference": {"upload_id": "u-1", **declared},
        "url": f"https://{STORAGE_HOST}/payload",
        "headers": {"If-None-Match": "*"},
    }


def payload_routes(storage: Any, *, reference: Any = upload_answer) -> Routes:
    return {
        ("POST", "/functions/f-1/runs/r-1/payloads/logs/upload"): reference,
        ("POST", "/functions/f-1/runs/r-1/payloads/result/upload"): reference,
        ("PUT", "storage"): storage,
        ("PATCH", "/functions/f-1/runs/r-1"): UPDATED_RUN,
    }


async def update_large_run(c: Any, wait: Any) -> Any:
    return await wait(
        c.functions.run_update_metadata("f-1", "r-1", status="closed", logs=["log"] * 20, result="r" * 50)
    )


@pytest.mark.asyncio
async def test_large_fields_are_uploaded_with_the_same_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_payloads, "INLINE_FIELD_BYTES", 10)
    exchange = await same_exchange(monkeypatch, payload_routes(b""), update_large_run)
    assert exchange.outcome[0] == "ok"
    methods = [(call.method, call.url) for call in exchange.calls]
    assert methods == [
        ("POST", f"{SERVER}/functions/f-1/runs/r-1/payloads/result/upload"),
        ("PUT", f"https://{STORAGE_HOST}/payload"),
        ("POST", f"{SERVER}/functions/f-1/runs/r-1/payloads/logs/upload"),
        ("PUT", f"https://{STORAGE_HOST}/payload"),
        ("PATCH", f"{SERVER}/functions/f-1/runs/r-1"),
    ]
    put = exchange.calls[1]
    assert "Authorization" not in put.headers and "x-notte-sdk-version" not in put.headers
    assert (b"Content-Length", str(len(json.dumps("r" * 50))).encode()) in exchange.headers[1]
    body = json.loads(exchange.calls[-1].data)
    assert set(body["payloads"]) == {"result", "logs"} and body["result_preview"] == "r" * 50


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["status", "redirect", "reference"])
async def test_upload_failure_never_finalizes_the_run(monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    monkeypatch.setattr(run_payloads, "INLINE_FIELD_BYTES", 10)
    storage = {
        "status": httpx.Response(503),
        "redirect": httpx.Response(307, headers={"location": "https://elsewhere.test/object"}),
        "reference": b"",
    }[failure]

    def wrong_reference(request: httpx.Request) -> dict[str, Any]:
        answer = upload_answer(request)
        answer["reference"]["size_bytes"] += 1
        return answer

    routes = payload_routes(storage, reference=wrong_reference if failure == "reference" else upload_answer)
    exchange = await same_exchange(monkeypatch, routes, update_large_run)
    assert exchange.outcome[0] == "error"
    assert all(call.method != "PATCH" for call in exchange.calls)
    if failure == "status":
        assert exchange.outcome[1].__name__ == "NotteHTTPStatusError"


def stored_run(raw: bytes, *, declared: bytes | None = None) -> dict[str, Any]:
    declared = raw if declared is None else declared
    reference = {"upload_id": "u-1", "size_bytes": len(declared), "sha256": checksum(declared)}
    return {
        **RUN,
        "payloads": {"logs": reference},
        "payload_urls": {"logs": f"https://{STORAGE_HOST}/logs"},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "checksum", "truncated", "oversized", "status", "missing_url", "http"])
async def test_payload_downloads_are_verified_the_same_way(
    monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    raw = json.dumps(["one", "two"]).encode()
    delivered = {
        "checksum": raw.replace(b"one", b"bad"),
        "truncated": raw[:-1],
        "oversized": raw + b" ",
    }.get(failure or "", raw)
    run = stored_run(raw)
    if failure == "missing_url":
        run["payload_urls"] = {}
    if failure == "http":
        run["payload_urls"] = {"logs": f"http://{STORAGE_HOST}/logs"}
    storage = httpx.Response(204) if failure == "status" else delivered
    routes = {("GET", "/functions/f-1/runs/r-1"): run, ("GET", "storage"): storage}

    async def flow(c: Any, wait: Any) -> Any:
        return await wait(c.functions.run_get_metadata("f-1", "r-1"))

    exchange = await same_exchange(monkeypatch, routes, flow)
    if failure is None:
        assert exchange.outcome[0] == "ok" and exchange.outcome[1]["logs"] == ["one", "two"]
    else:
        assert exchange.outcome[0] == "error" and exchange.outcome[1] is ValueError
    storage_calls = [call for call in exchange.calls if STORAGE_HOST in call.url]
    assert len(storage_calls) == (0 if failure in ("missing_url", "http") else 1)
    assert all("Authorization" not in call.headers for call in storage_calls)
    assert exchange.calls[0].params == {"payload_mode": "references"}


@pytest.mark.asyncio
async def test_async_download_stops_reading_past_the_declared_size(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = json.dumps(["one", "two"]).encode()
    consumed: list[bytes] = []

    class Chunks(httpx.AsyncByteStream):
        async def __aiter__(self):  # pyright: ignore[reportIncompatibleMethodOverride]
            for chunk in (raw, b" " * (64 * 1024), b"never read"):
                consumed.append(chunk)
                yield chunk

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=Chunks())

    monkeypatch.setattr("notte_sdk._transport.async_http_client", lambda: _mocked_async(handle))
    with pytest.raises(ValueError, match="exceeds its declared size"):
        _ = await run_payloads.aresolve_run_fields(stored_run(raw))
    assert consumed == [raw, b" " * (64 * 1024)]


def _mocked_async(handle: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handle))


# ---------------------------------------------------------------------------
# Files: the same requests


def file_routes(pages: list[list[dict[str, Any]]]) -> Routes:
    def listing(request: httpx.Request) -> Any:
        offset = int(request.url.params.get("offset", "0"))
        total = sum(len(page) for page in pages)
        index = 0 if offset == 0 else next(i for i in range(len(pages)) if sum(len(p) for p in pages[:i]) == offset)
        return {"files": pages[index], "total": total, "limit": 1000, "offset": offset}

    return {
        ("GET", "/sessions/s-1/files"): listing,
        ("POST", "/sessions/s-1/files"): file_entry("file-new", "notes.txt"),
        ("GET", "/sessions/s-1/files/file-2"): b"hello",
        ("GET", "/sessions/s-1/files/file-1"): b"first",
        ("DELETE", "/sessions/s-1/files/file-1"): {},
    }


def file_flows(tmp_path: Path, upload: str) -> dict[str, Flow]:
    async def upload_file(c: Any, wait: Any) -> Any:
        return await wait(c.files.upload("s-1", upload, "renamed.txt"))

    async def upload_missing(c: Any, wait: Any) -> Any:
        return await wait(c.files.upload("s-1", str(tmp_path / "missing.txt")))

    async def metadata_on_page_two(c: Any, wait: Any) -> Any:
        return await wait(c.files.metadata("s-1", "file-2"))

    async def metadata_missing(c: Any, wait: Any) -> Any:
        return await wait(c.files.metadata("s-1", "file-9"))

    async def download(c: Any, wait: Any) -> Any:
        path = await wait(c.files.download("s-1", "file-2", str(tmp_path / "out"), force=True))
        return [path, Path(path).read_bytes().decode()]

    async def download_existing(c: Any, wait: Any) -> Any:
        directory = tmp_path / "existing"
        directory.mkdir(exist_ok=True)
        (directory / "second.txt").write_text("keep")
        return await wait(c.files.download("s-1", "file-2", str(directory)))

    async def storage(c: Any, wait: Any) -> Any:
        store = c.FileStorage("s-1")
        uploaded = await wait(store.upload(upload))
        listed = await wait(store.list())
        local = await wait(store.get_file("input.txt"))
        missing = await wait(store.get_file("nothing.txt"))
        stored = await wait(store.set_file(upload))
        infos = [await wait(store.list_uploaded_files()), await wait(store.list_downloaded_files())]
        instructions = await wait(store.instructions())
        await wait(store.delete("file-1"))
        return [uploaded, listed, Path(local).read_text(), missing, stored, infos, instructions]

    return {name: flow for name, flow in locals().items() if name not in ("tmp_path", "upload")}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name",
    [
        "upload_file",
        "upload_missing",
        "metadata_on_page_two",
        "metadata_missing",
        "download",
        "download_existing",
        "storage",
    ],
)
async def test_files_send_the_same_requests(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, upload: str, name: str
) -> None:
    pages = [[file_entry("file-1")], [file_entry("file-2", "second.txt", "session_download")]]
    monkeypatch.setattr(files_module, "NOTTE_CACHE_DIR", tmp_path / "cache")
    routes = file_routes(pages)
    flow = file_flows(tmp_path, upload)[name]
    if name == "upload_missing":
        exchange = exchange_sync(monkeypatch, Api(routes), lambda c: _drive(flow(c, _passthrough)))
        assert exchange.outcome[1] is FileNotFoundError and not exchange.calls
        assert await exchange_async(monkeypatch, Api(routes), lambda c: flow(c, _await)) == exchange
        return
    exchange = await same_exchange(monkeypatch, routes, flow)
    if name in ("metadata_missing", "download_existing"):
        assert (
            exchange.outcome[1] is {"metadata_missing": FileNotFoundError, "download_existing": FileExistsError}[name]
        )
    else:
        assert exchange.outcome[0] == "ok", exchange.outcome
    if name == "upload_file":
        assert exchange.calls[0].files == {"file": ("renamed.txt", b"upload-data", "text/plain")}
    if name == "download":
        assert exchange.outcome[1][1] == "hello"
        assert not list((tmp_path / "out").glob("*.part"))


# ---------------------------------------------------------------------------
# No local file I/O on the event loop


class OffLoop:
    """Wraps a file object: every call made on the event loop's thread fails the test."""

    def __init__(self, wrapped: Any, loop_thread: int, violations: list[str]) -> None:
        self._wrapped, self._loop_thread, self._violations = wrapped, loop_thread, violations

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._wrapped, name)
        if not callable(value):
            return value

        def call(*args: Any, **kwargs: Any) -> Any:
            if threading.get_ident() == self._loop_thread:
                self._violations.append(name)
            return value(*args, **kwargs)

        return call

    def __enter__(self) -> "OffLoop":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


@pytest.mark.asyncio
async def test_local_files_are_read_and_written_off_the_event_loop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, upload: str, code: str
) -> None:
    loop_thread = threading.get_ident()
    violations: list[str] = []

    def guarded(factory: Callable[..., Any]) -> Callable[..., Any]:
        def open_file(*args: Any, **kwargs: Any) -> Any:
            if threading.get_ident() == loop_thread:
                violations.append(f"opened {args[:1]}")
            return OffLoop(factory(*args, **kwargs), loop_thread, violations)

        return open_file

    # Every local file the async client opens: uploads, downloads, run payload spools and function code.
    monkeypatch.setattr(base_module, "open", guarded(open), raising=False)
    monkeypatch.setattr(files_module.tempfile, "NamedTemporaryFile", guarded(files_module.tempfile.NamedTemporaryFile))
    monkeypatch.setattr(run_payloads, "TemporaryFile", guarded(run_payloads.TemporaryFile))
    monkeypatch.setattr("notte_sdk.endpoints.functions.open", guarded(open), raising=False)
    monkeypatch.setattr(run_payloads, "INLINE_FIELD_BYTES", 10)
    monkeypatch.setattr(files_module, "NOTTE_CACHE_DIR", tmp_path / "cache")
    raw = json.dumps(["one", "two"]).encode()
    routes = {
        **run_routes(),
        **file_routes([[file_entry("file-1")]]),
        **payload_routes(b""),
        ("GET", "/functions/f-1/runs/r-1"): stored_run(raw),
    }

    def storage(request: httpx.Request) -> Any:
        return raw if request.url.path == "/logs" else CODE.encode()

    routes[("GET", "storage")] = storage

    async def flow(c: AsyncNotteClient) -> Any:
        _ = await c.files.upload("s-1", upload)
        _ = await c.files.download("s-1", "file-1", str(tmp_path / "out"), force=True)
        _ = await c.functions.update("f-1", path=code)
        _ = await c.functions.run_update_metadata("f-1", "r-1", status="closed", logs=["log"] * 20)
        run = await c.functions.run_get_metadata("f-1", "r-1")
        _ = await c.Function("f-1").download(str(tmp_path / "code.py"))
        _ = await c.sessions.request_download(f"https://{STORAGE_HOST}/code.py", str(tmp_path / "plain.py"))
        return run.logs

    exchange = await exchange_async(monkeypatch, Api(routes), flow)
    assert exchange.outcome == ("ok", ["one", "two"])
    assert violations == []
    assert (tmp_path / "code.py").read_text() == CODE == (tmp_path / "plain.py").read_text()


@pytest.mark.asyncio
async def test_request_download_matches_sync(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    routes = {("GET", "storage"): b"x" * 20000}

    async def flow(c: Any, wait: Any) -> Any:
        target = tmp_path / "file.bin"
        ok = await wait(c.sessions.request_download(f"https://{STORAGE_HOST}/file.bin", str(target)))
        return [ok, target.read_bytes() == b"x" * 20000]

    exchange = await same_exchange(monkeypatch, routes, flow)
    assert exchange.outcome == ("ok", [True, True])
    # Public downloads carry no API credentials.
    assert "Authorization" not in exchange.calls[0].headers
    missing = {("GET", "storage"): httpx.Response(404)}
    failed = await same_exchange(monkeypatch, missing, flow)
    assert failed.outcome[1].__name__ == "NotteHTTPStatusError"


# ---------------------------------------------------------------------------
# Cancelled while a worker thread creates a file: nothing is left behind


class Blocking:
    """A file factory whose worker thread waits until released, so the caller can be cancelled meanwhile."""

    def __init__(self, factory: Callable[..., Any]) -> None:
        self.factory: Callable[..., Any] = factory
        self.started: threading.Event = threading.Event()
        self.release: threading.Event = threading.Event()
        self.done: threading.Event = threading.Event()
        self.created: list[Any] = []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.started.set()
        assert self.release.wait(5)
        created = self.factory(*args, **kwargs)
        self.created.append(created)
        self.done.set()
        return created

    async def cancel_while_creating(self, call: Coroutine[Any, Any, Any]) -> Any:
        """Cancel `call` while its worker creates the file; returns what the worker created."""
        task = asyncio.ensure_future(call)
        assert await asyncio.to_thread(self.started.wait, 5)
        _ = task.cancel()
        self.release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        # Without ownership of the worker's result, the task ends before the worker does.
        assert await asyncio.to_thread(self.done.wait, 5)
        return self.created[0]


@pytest.mark.asyncio
async def test_cancelled_download_leaves_no_partial_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    blocking = Blocking(files_module._partial_file)
    monkeypatch.setattr(files_module, "_partial_file", blocking)
    pages = [[file_entry("file-2", "second.txt")]]
    client = async_http_client()
    client._transport = httpx.MockTransport(Api(file_routes(pages)))
    monkeypatch.setattr(AsyncSharedHttpClient, "get", lambda _: client)
    notte = AsyncNotteClient(api_key=KEY, server_url=SERVER)
    output = await blocking.cancel_while_creating(notte.files.download("s-1", "file-2", str(tmp_path)))
    assert output.closed
    assert list(tmp_path.iterdir()) == []
    await client.aclose()


@pytest.mark.asyncio
async def test_cancelled_request_download_closes_its_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    blocking = Blocking(open)
    monkeypatch.setattr(base_module, "open", blocking, raising=False)
    client = async_http_client()
    client._transport = httpx.MockTransport(Api({("GET", "storage"): b"body"}))
    monkeypatch.setattr(AsyncSharedHttpClient, "get", lambda _: client)
    notte = AsyncNotteClient(api_key=KEY, server_url=SERVER)
    call = notte.sessions.request_download(f"https://{STORAGE_HOST}/file", str(tmp_path / "file"))
    assert (await blocking.cancel_while_creating(call)).closed
    await client.aclose()


@pytest.mark.asyncio
async def test_cancelled_payload_spool_closes_its_file(monkeypatch: pytest.MonkeyPatch) -> None:
    blocking = Blocking(run_payloads._spool)
    monkeypatch.setattr(run_payloads, "_spool", blocking)
    monkeypatch.setattr(run_payloads, "INLINE_FIELD_BYTES", 1)
    notte = AsyncNotteClient(api_key=KEY, server_url=SERVER)
    call = run_payloads.aoffload_run_fields(notte.functions, "f-1", "r-1", {"logs": ["log"]})
    payload, _, _ = await blocking.cancel_while_creating(call)
    assert payload.closed


@pytest.mark.asyncio
async def test_cancelled_payload_download_closes_its_file(monkeypatch: pytest.MonkeyPatch) -> None:
    blocking = Blocking(run_payloads._PayloadDownload)
    monkeypatch.setattr(run_payloads, "_PayloadDownload", blocking)
    download = await blocking.cancel_while_creating(run_payloads.aresolve_run_fields(stored_run(b"[]")))
    assert download._file.closed


@pytest.mark.asyncio
async def test_per_call_clients_build_their_ssl_context_off_the_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    from notte_sdk import _transport

    loop_thread = threading.get_ident()
    threads: list[int] = []
    ssl_context = _transport._ssl_context

    def recording_ssl_context() -> Any:
        threads.append(threading.get_ident())
        return ssl_context()

    def storage(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"body")

    real_client = _transport.async_http_client
    monkeypatch.setattr(_transport, "_ssl_context", recording_ssl_context)
    # The real client, which reads the CA bundle, answered in place of the network.
    monkeypatch.setattr(_transport, "async_http_client", lambda: mocked(real_client(), storage))
    url = f"https://{STORAGE_HOST}/object"
    assert await _transport.aget_text(url, timeout=5) == "body"
    assert await _transport.aput_object(url, io.BytesIO(b"x"), headers={}, timeout=(5, 5)) == 200
    async with _transport.aget_object(url, timeout=(5, 5), chunk_size=4) as (status, chunks):
        assert (status, b"".join([chunk async for chunk in chunks])) == (200, b"body")
    assert len(threads) == 3
    assert loop_thread not in threads
