"""`AsyncNotteClient` resources: the sync resource methods, as coroutines, sending the same requests.

The parity helpers here (`afake`, `exchange_sync`/`exchange_async`) are shared with
`test_async_transport.py`.
"""

import asyncio
import inspect
import random
import sys
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
from notte_sdk import AsyncNotteClient, NotteClient
from notte_sdk._generated import resources
from notte_sdk._transport import AsyncSharedHttpClient, SharedHttpClient, async_http_client, http_client
from notte_sdk._v1_aliases import _RENAMED_METHODS
from notte_sdk.actions import Goto
from notte_sdk.endpoints.base import AsyncBaseClient, BaseClient
from notte_sdk.endpoints.vaults import VaultsClient
from pydantic import BaseModel
from pydantic_core import to_json

from tests.sdk.test_generated_endpoints import PERSONA, PROFILE, SERVER, VAULT, Body, Call, FakeSession

KEY = "test-api-key"  # pragma: allowlist secret
STAMP = "2026-10-13T00:00:00Z"
SESSION = dict(session_id="s-1", idle_timeout_minutes=3, created_at=STAMP, last_accessed_at=STAMP, status="active")
FUNCTION = dict(
    function_id="f-1", created_at=STAMP, updated_at=STAMP, latest_version="v1", versions=["v1"], status="active"
)
RUN = dict(function_id="f-1", function_run_id="r-1", created_at=STAMP, updated_at=STAMP, status="active")
PAGE = dict(page=1, page_size=10, has_next=False, has_previous=False)
RESOURCES = ("sessions", "functions", "files", "personas", "profiles", "vaults")

# Sync resource members that `AsyncNotteClient` does not have yet: the methods the hand-written
# sync clients add or override with more than the wire call. The async stateful layer ports
# them; remove each entry as its async twin lands.
PENDING = {
    "sessions": set(),
    "functions": set(),
    "files": set(),
    "personas": set(),
    "profiles": set(),
    "vaults": set(),
}
# Async resource methods that stay plain methods: they only format text and send nothing.
NOT_COROUTINES = {"functions": {"decode_message", "get_curl"}}


@pytest.fixture(autouse=True)
def without_ci_vault_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    # In CI, tests/conftest.py wraps sync and async `vaults.create` to name and record the vaults a
    # run creates. That wrapper is not SDK behavior: restore the generated methods, and keep these
    # fake vaults out of the cleanup list.
    scope = sys.modules.get("ci_vault_scope")
    if scope is None or not getattr(scope, "_installed", False):
        return
    monkeypatch.setattr(scope, "record_vault_id", lambda *_: pytest.fail("Fake vault must not enter CI cleanup"))
    monkeypatch.delattr(VaultsClient, "create")
    monkeypatch.setattr(resources.AsyncVaultsOperations, "create", resources.AsyncVaultsOperations.create.__wrapped__)


# ---------------------------------------------------------------------------
# An async `fake()`


class DualBody(Body, httpx.AsyncByteStream):
    """A response body either client can read; records whether it was closed."""

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self.content

    async def aclose(self) -> None:
        self.closed = True


class AsyncFakeSession(FakeSession):
    """`FakeSession` for `AsyncNotteClient`: answers every request in place of the API and records it."""

    def __init__(self, payload: Any, status_code: int = 200) -> None:
        super().__init__(payload, status_code)
        self.async_client: httpx.AsyncClient = httpx.AsyncClient(transport=httpx.MockTransport(self._handle))

    def _handle(self, request: httpx.Request) -> httpx.Response:
        response = super()._handle(request)
        body = DualBody(self.bodies[-1].content)
        self.bodies[-1] = body
        return httpx.Response(response.status_code, headers=response.headers, stream=body)


def afake(monkeypatch: pytest.MonkeyPatch, payload: Any, status_code: int = 200) -> AsyncFakeSession:
    """`fake()` for `AsyncNotteClient`: every async request is answered with `payload`."""
    session = AsyncFakeSession(payload, status_code)
    monkeypatch.setattr("notte_sdk._transport.AsyncSharedHttpClient.get", lambda _: session.async_client)
    return session


@pytest.fixture
def aclient() -> AsyncNotteClient:
    return AsyncNotteClient(api_key=KEY, server_url=SERVER)


@pytest.mark.asyncio
async def test_afake_records_async_requests(aclient: AsyncNotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    api = afake(monkeypatch, PERSONA)
    assert (await aclient.personas.get("persona-1")).persona_id == "persona-1"
    assert [(call.method, call.url) for call in api.calls] == [("GET", f"{SERVER}/personas/persona-1")]
    assert all(body.closed for body in api.bodies)


# ---------------------------------------------------------------------------
# Same methods, same signatures


def members(cls: type) -> set[str]:
    """Public methods defined on `cls` itself."""
    return {
        name
        for name, value in vars(cls).items()
        if not name.startswith("_") and (inspect.isfunction(value) or isinstance(value, staticmethod))
    }


def resource_classes(name: str) -> tuple[type, type, type]:
    """The sync client class, its generated base and the async generated class of a resource."""
    sync = type(getattr(NotteClient(api_key=KEY, server_url=SERVER), name))
    generated = next(cls for cls in sync.__mro__ if cls.__module__ == resources.__name__)
    return sync, generated, getattr(resources, f"Async{generated.__name__}")


def async_client_class(name: str) -> type:
    """The class of `AsyncNotteClient().<name>`: the async generated class, or a hand-written subclass."""
    return type(getattr(AsyncNotteClient(api_key=KEY, server_url=SERVER), name))


def resource_members(cls: type, stop: type) -> set[str]:
    """Public methods of a resource class, without those of `BaseClient` / `AsyncBaseClient`."""
    return set().union(*(members(base) for base in cls.__mro__[: cls.__mro__.index(stop)]))


@pytest.mark.parametrize("name", RESOURCES)
def test_async_resources_have_the_sync_methods_except_the_pending_ones(name: str) -> None:
    sync, generated, async_generated = resource_classes(name)
    resource = getattr(AsyncNotteClient(api_key=KEY, server_url=SERVER), name)
    generated_methods = resource_members(generated, BaseClient)
    # Methods the hand-written client defines (new or overriding a generated one), and its
    # `PageClient`. The deprecated 1.x aliases are not carried over to the new client.
    handwritten = resource_members(sync, generated) - set(_RENAMED_METHODS.get(sync, {}))
    handwritten |= {"page"} & set(vars(getattr(NotteClient(api_key=KEY, server_url=SERVER), name)))
    async_methods = resource_members(type(resource), AsyncBaseClient) | ({"page"} & set(vars(resource)))
    # Every generated method has an async twin, unless the sync client overrides it and its
    # async override is still pending.
    assert resource_members(async_generated, AsyncBaseClient) == generated_methods - (handwritten & PENDING[name])
    # The async resource has nothing the sync one lacks, and the pinned list of what it is still missing.
    assert async_methods <= generated_methods | handwritten
    assert (generated_methods | handwritten) - async_methods == PENDING[name]


@pytest.mark.parametrize("name", RESOURCES)
def test_async_twins_have_the_same_signatures(name: str) -> None:
    sync = resource_classes(name)[0]
    async_ = async_client_class(name)
    for method in resource_members(async_, AsyncBaseClient):
        # The sync client's method: generated, or the hand-written override.
        sync_method = getattr(sync, method)
        async_method = getattr(async_, method)
        assert inspect.iscoroutinefunction(async_method) is (method not in NOT_COROUTINES.get(name, set())), method
        assert not inspect.iscoroutinefunction(sync_method), method
        assert inspect.signature(async_method) == inspect.signature(sync_method), method
        assert inspect.getdoc(async_method) == inspect.getdoc(sync_method), method


def test_async_client_has_the_sync_constructor() -> None:
    assert inspect.signature(AsyncNotteClient.__init__) == inspect.signature(NotteClient.__init__)
    client = AsyncNotteClient(api_key=KEY, server_url=SERVER, max_retries=1, captcha_timeout_seconds=5)
    assert (client.max_retries, client.captcha_timeout_seconds) == (1, 5)
    for name in RESOURCES:
        resource = getattr(client, name)
        assert isinstance(resource, AsyncBaseClient)
        assert resource.root_client is client
        assert resource.base_endpoint_path == getattr(NotteClient(api_key=KEY), name).base_endpoint_path
    with pytest.raises(ValueError, match="max_retries"):
        _ = AsyncNotteClient(api_key=KEY, max_retries=-1)
    with pytest.raises(ValueError, match="captcha_timeout_seconds"):
        _ = AsyncNotteClient(api_key=KEY, captcha_timeout_seconds=0)


# ---------------------------------------------------------------------------
# Same requests: one handler answers both clients behind their real transport configuration


@dataclass
class Exchange:
    """What a call sent and what it returned or raised."""

    calls: list[Call]
    # Every header on the wire, except a multipart body's random boundary and length.
    headers: list[list[tuple[bytes, bytes]]]
    outcome: tuple[Any, ...]
    sleeps: list[float] = field(default_factory=list)


def normalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, (list, tuple)):
        return [normalize(item) for item in value]
    return value


def wire_headers(request: httpx.Request) -> list[tuple[bytes, bytes]]:
    multipart = request.headers.get("content-type", "").startswith("multipart/form-data")
    return [
        (name, value)
        for name, value in request.headers.raw
        if not (multipart and name.lower() in (b"content-type", b"content-length"))
    ]


def recorder(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[list[httpx.Request], Callable[[httpx.Request], httpx.Response]]:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return seen, handle


def mocked(client: Any, handle: Callable[[httpx.Request], httpx.Response]) -> Any:
    client._transport = httpx.MockTransport(handle)
    return client


def exchange_sync(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
    call: Callable[[Any], Any],
    *,
    max_retries: int = 0,
) -> Exchange:
    seen, handle = recorder(handler)
    client = http_client()
    client._transport = httpx.MockTransport(handle)
    sleeps: list[float] = []
    with monkeypatch.context() as patch:
        patch.setattr(SharedHttpClient, "get", lambda _: client)
        # Object storage and public downloads use their own clients.
        patch.setattr("notte_sdk._transport.http_client", lambda: mocked(http_client(), handle))
        patch.setattr("notte_sdk._transport.time.sleep", sleeps.append)
        random.seed(0)
        notte = NotteClient(api_key=KEY, server_url=SERVER, max_retries=max_retries)
        try:
            outcome: tuple[Any, ...] = ("ok", normalize(call(notte)))
        except Exception as error:
            outcome = ("error", type(error), str(error))
    return Exchange([Call.from_request(r) for r in seen], [wire_headers(r) for r in seen], outcome, sleeps)


async def exchange_async(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
    call: Callable[[Any], Any],
    *,
    max_retries: int = 0,
) -> Exchange:
    seen, handle = recorder(handler)
    client = async_http_client()
    client._transport = httpx.MockTransport(handle)
    sleeps: list[float] = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    with monkeypatch.context() as patch:
        patch.setattr(AsyncSharedHttpClient, "get", lambda _: client)
        patch.setattr("notte_sdk._transport.async_http_client", lambda: mocked(async_http_client(), handle))
        patch.setattr("notte_sdk._transport.asyncio.sleep", sleep)
        random.seed(0)
        notte = AsyncNotteClient(api_key=KEY, server_url=SERVER, max_retries=max_retries)
        try:
            outcome: tuple[Any, ...] = ("ok", normalize(await call(notte)))
        except Exception as error:
            outcome = ("error", type(error), str(error))
    await client.aclose()
    return Exchange([Call.from_request(r) for r in seen], [wire_headers(r) for r in seen], outcome, sleeps)


async def assert_same_exchange(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
    call: Callable[[Any], Any],
    *,
    max_retries: int = 0,
) -> Exchange:
    expected = exchange_sync(monkeypatch, handler, call, max_retries=max_retries)
    actual = await exchange_async(monkeypatch, handler, call, max_retries=max_retries)
    assert actual == expected
    return expected


def answer(payload: Any, status_code: int = 200) -> Callable[[httpx.Request], httpx.Response]:
    content = payload if isinstance(payload, bytes) else to_json(payload)
    return lambda request: httpx.Response(status_code, content=content)


@pytest.fixture
def upload(tmp_path: Path) -> str:
    path = tmp_path / "notes.txt"
    _ = path.write_text("upload-data")
    return str(path)


# (call, response payload) pairs: paths, query strings, JSON and multipart bodies, headers,
# timeouts and SDK-side defaults. Each runs through both clients.
SAMPLE: list[tuple[str, Callable[[Any, str], Any], Any]] = [
    ("sessions.list", lambda c, f: c.sessions.list(page_size=5, include_system=True), {**PAGE, "items": [SESSION]}),
    ("sessions.start", lambda c, f: c.sessions.start(proxies=True, max_duration_minutes=5), SESSION),
    ("sessions.status", lambda c, f: c.sessions.status("s/1"), SESSION),
    ("sessions.auth_readiness", lambda c, f: c.sessions.auth_readiness("s-1"), {"status": "ready"}),
    (
        "sessions.create_payment",
        lambda c, f: c.sessions.create_payment(
            "s-1",
            idempotency_key="key-1",
            query={"update_metadata": True},
            amount=10,
            currency="usd",
            merchant_url="https://shop.example",
            merchant_name="Shop",
            description="order",
        ),
        {"payment_id": "pay-1"},
    ),
    ("sessions.upload_session_file", lambda c, f: c.sessions.upload_session_file("s-1", file=f), {"id": "file-1"}),
    ("sessions.download_session_file", lambda c, f: c.sessions.download_session_file("s-1", "file-1"), b"\x00bytes"),
    ("sessions.page_screenshot", lambda c, f: c.sessions.page_screenshot("s-1", update_metadata=True), {"x": 1}),
    ("sessions.execute", lambda c, f: c.sessions.execute("s-1", Goto(url="https://example.com")), {"success": True}),
    ("sessions.observe", lambda c, f: c.sessions.observe("s-1", min_nb_actions=2), {"x": 1}),
    ("sessions.scrape", lambda c, f: c.sessions.scrape("s-1", only_main_content=False), {"markdown": "# x"}),
    ("sessions.get_cookies", lambda c, f: c.sessions.get_cookies("s-1"), {"cookies": []}),
    ("sessions.delete_session_file", lambda c, f: c.sessions.delete_session_file("s-1", "file-1"), {}),
    ("profiles.list", lambda c, f: c.profiles.list(), {"items": [PROFILE], "page": 1, "page_size": 20}),
    ("profiles.delete", lambda c, f: c.profiles.delete("p-1"), {"success": True, "message": "deleted"}),
    ("vaults.list", lambda c, f: c.vaults.list(), {"items": [VAULT], "page": 1, "page_size": 10}),
    (
        "vaults.credentials_add",
        lambda c, f: c.vaults.credentials_add("v-1", url="https://x.test", email="a@x.test", password="pw"),
        {"status": "success"},
    ),
    ("vaults.credit_card_get", lambda c, f: c.vaults.credit_card_get("v-1"), {"credit_card": None}),
    ("vaults.delete", lambda c, f: c.vaults.delete("v-1"), {"status": "success", "message": "gone"}),
    ("functions.create", lambda c, f: c.functions.create(path=f, query={"restricted": False}), FUNCTION),
    ("functions.list", lambda c, f: c.functions.list(page_size=2), {**PAGE, "items": [FUNCTION]}),
    ("functions.list_runs", lambda c, f: c.functions.list_runs("f-1"), {**PAGE, "items": [RUN]}),
    (
        "functions.rollback",
        lambda c, f: c.functions.rollback("f-1", version="v1", query={"restricted": True}),
        FUNCTION,
    ),
    ("functions.download_run_payload", lambda c, f: c.functions.download_run_payload("f-1", "r-1", "x"), [1]),
    (
        "functions.prepare_run_payload_upload",
        lambda c, f: c.functions.prepare_run_payload_upload("f-1", "r-1", "x", size_bytes=3, sha256="ab"),
        {"upload_id": "u-1"},
    ),
    ("functions.set_schedule", lambda c, f: c.functions.set_schedule("f-1", cron="* * * * *", variables=None), {}),
    ("personas.create", lambda c, f: c.personas.create(create_vault=False), PERSONA),
    ("personas.emails_list", lambda c, f: c.personas.emails_list("p-1", only_unread=True, limit=5), []),
    ("files.list", lambda c, f: c.files.list("s-1", limit=10, source="upload"), {"files": [], "total": 0}),
    ("files.delete", lambda c, f: c.files.delete("s-1", "file-1"), {}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("call", [entry[1] for entry in SAMPLE], ids=[entry[0] for entry in SAMPLE])
@pytest.mark.parametrize("status", [200, 404])
async def test_sample_sends_the_same_requests_and_returns_the_same_results(
    monkeypatch: pytest.MonkeyPatch, upload: str, call: Callable[[Any, str], Any], status: int
) -> None:
    payload = next(entry[2] for entry in SAMPLE if entry[1] is call)
    exchange = await assert_same_exchange(
        monkeypatch, answer(payload if status == 200 else {"detail": "missing"}, status), lambda c: call(c, upload)
    )
    assert len(exchange.calls) == 1


@pytest.mark.asyncio
async def test_sample_covers_bodies_queries_headers_and_timeouts(monkeypatch: pytest.MonkeyPatch, upload: str) -> None:
    calls = {
        name: (await assert_same_exchange(monkeypatch, answer(payload), lambda c, call=call: call(c, upload))).calls[0]
        for name, call, payload in SAMPLE
    }
    assert calls["sessions.status"].url == f"{SERVER}/sessions/s%2F1"
    assert calls["sessions.list"].params == {"page_size": "5", "include_system": "True"}
    assert calls["profiles.list"].params == {"page_size": "20"}
    assert calls["functions.list_runs"].params == {"only_active": "True"}
    assert calls["sessions.create_payment"].headers["idempotency-key"] == "key-1"
    assert calls["sessions.create_payment"].params == {"update_metadata": "True"}
    assert calls["sessions.auth_readiness"].timeout == {"connect": 10, "read": 10, "write": 10, "pool": 10}
    assert calls["sessions.status"].timeout == {"connect": 60, "read": 60, "write": 60, "pool": 60}
    assert calls["sessions.upload_session_file"].files == {"file": ("notes.txt", b"upload-data", "text/plain")}
    assert calls["functions.create"].files["file"][1] == b"upload-data"
    assert calls["functions.create"].params == {"restricted": "False"}
    assert calls["vaults.credentials_add"].data is not None
    assert '"credentials"' in calls["vaults.credentials_add"].data


def arguments(method: Callable[..., Any]) -> tuple[list[Any], dict[str, Any]]:
    """Minimal arguments for any resource method: placeholder path parameters, no optional keywords."""
    args: list[Any] = []
    kwargs: dict[str, Any] = {}
    for parameter in inspect.signature(method).parameters.values():
        if parameter.name == "self" or parameter.kind is parameter.VAR_KEYWORD:
            continue
        if parameter.default is not parameter.empty:
            continue
        if parameter.name == "body":
            args.append(Goto(url="https://example.com"))
        elif parameter.kind is parameter.POSITIONAL_OR_KEYWORD:
            args.append(f"{parameter.name}-1")
        else:
            kwargs[parameter.name] = f"{parameter.name}-1"
    return args, kwargs


def every_async_method() -> Iterator[tuple[str, str]]:
    for name in RESOURCES:
        for method in sorted(resource_members(async_client_class(name), AsyncBaseClient)):
            # Plain methods send nothing; the signature test covers them.
            if method not in NOT_COROUTINES.get(name, set()):
                yield name, method


# Methods whose `**data` needs a local file: the keyword that takes its path.
FILE_KEYWORDS = {
    ("functions", "create"): "path",
    ("functions", "update"): "path",
    ("files", "upload"): "file_path",
    ("sessions", "upload_session_file"): "file",
}
# Methods that refuse to send without one of their optional arguments, and the viewer that only
# fetches its URL when none is given.
REQUIRED_KEYWORDS: dict[tuple[str, str], dict[str, Any]] = {
    ("sessions", "set_cookies"): {"cookies": []},
    ("sessions", "viewer_browser"): {"_viewer_url": None},
}


@pytest.mark.asyncio
@pytest.mark.parametrize("resource,method", list(every_async_method()), ids=lambda value: value)
async def test_every_async_method_sends_what_its_sync_twin_sends(
    monkeypatch: pytest.MonkeyPatch, upload: str, resource: str, method: str
) -> None:
    # The viewers open a local browser tab: never from a test.
    monkeypatch.setattr("notte_sdk.endpoints.sessions.open_browser", lambda *_args, **_kwargs: True)
    bound = getattr(getattr(AsyncNotteClient(api_key=KEY), resource), method)
    args, kwargs = arguments(bound)
    # The positional arguments `arguments()` filled: the required ones, in order.
    positional = [
        parameter.name
        for parameter in inspect.signature(bound).parameters.values()
        if parameter.kind is parameter.POSITIONAL_OR_KEYWORD and parameter.default is parameter.empty
    ]
    overrides = dict(REQUIRED_KEYWORDS.get((resource, method), {}))
    if keyword := FILE_KEYWORDS.get((resource, method)):
        overrides[keyword] = upload
    for name, value in overrides.items():
        if name in positional:
            args[positional.index(name)] = value
        else:
            kwargs[name] = value
    exchange = await assert_same_exchange(
        monkeypatch, answer({}), lambda c: getattr(getattr(c, resource), method)(*args, **kwargs)
    )
    # Equal and empty would prove nothing: each case must reach the wire.
    assert exchange.calls, f"{resource}.{method} sent no request: {exchange.outcome}"


# ---------------------------------------------------------------------------
# Concurrency


@pytest.mark.asyncio
async def test_concurrent_calls_overlap(monkeypatch: pytest.MonkeyPatch) -> None:
    in_flight = 0
    peak = 0
    all_started = asyncio.Event()
    calls = 5

    async def handle(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        if in_flight == calls:
            all_started.set()
        # Every request waits until all of them are in flight: sequential calls would never finish.
        await asyncio.wait_for(all_started.wait(), timeout=5)
        in_flight -= 1
        return httpx.Response(200, json=SESSION)

    client = async_http_client()
    client._transport = httpx.MockTransport(handle)
    monkeypatch.setattr(AsyncSharedHttpClient, "get", lambda _: client)
    async with AsyncNotteClient(api_key=KEY, server_url=SERVER) as notte:
        results = await asyncio.gather(*(notte.sessions.status(f"s-{index}") for index in range(calls)))
    assert [result.session_id for result in results] == ["s-1"] * calls
    assert peak == calls
    await client.aclose()
