"""`AsyncNotteClient` sessions: `AsyncRemoteSession`, `AsyncSessionsClient` and `AsyncPageClient`.

They must have the sync methods as coroutines, send the same requests, sleep the same way and
return the same results; the async session also has to clean up on cancellation.
"""

import asyncio
import inspect
import json
import threading
import typing
from collections.abc import Awaitable, Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from notte_core.actions import ClickAction, GotoAction
from notte_core.observation import Observation, utc_now
from notte_sdk import AsyncNotteClient, NotteClient
from notte_sdk._transport import AsyncSharedHttpClient, async_http_client
from notte_sdk._v1_aliases import _RENAMED_METHODS
from notte_sdk.endpoints import sessions
from notte_sdk.endpoints.base import AsyncBaseClient, BaseClient, NotteEndpoint
from notte_sdk.endpoints.files import AsyncRemoteFileStorage, RemoteFileStorage
from notte_sdk.endpoints.page import AsyncPageClient, PageClient
from notte_sdk.endpoints.sessions import AsyncRemoteSession, AsyncSessionsClient, RemoteSession, SessionsClient
from notte_sdk.errors import NotteAPIError
from notte_sdk.types import CaptchaStatus, ExecutionResultResponse
from pydantic import BaseModel

from tests.sdk.test_async_functions_files import file_entry, file_routes, same_exchange
from tests.sdk.test_async_resources import KEY, SESSION, exchange_async, exchange_sync
from tests.sdk.test_generated_endpoints import PROFILE, SERVER

# ---------------------------------------------------------------------------
# Same methods, same signatures


def public_members(cls: type) -> dict[str, Any]:
    """Public methods and properties of `cls`, inherited ones included."""
    found: dict[str, Any] = {}
    for base in reversed(cls.__mro__[:-1]):
        for name, value in vars(base).items():
            if not name.startswith("_") and (inspect.isfunction(value) or isinstance(value, property)):
                found[name] = value
    return found


def same_signature(sync: Callable[..., Any], async_: Callable[..., Any]) -> None:
    assert inspect.iscoroutinefunction(async_), async_
    assert not inspect.iscoroutinefunction(sync), sync
    assert inspect.signature(async_) == inspect.signature(sync), sync.__qualname__
    sync_overloads = typing.get_overloads(inspect.unwrap(sync))
    async_overloads = typing.get_overloads(inspect.unwrap(async_))
    assert [inspect.signature(o) for o in async_overloads] == [inspect.signature(o) for o in sync_overloads]
    assert all(inspect.iscoroutinefunction(o) for o in async_overloads)


def test_async_session_has_the_sync_session_methods() -> None:
    sync_members = public_members(RemoteSession)
    async_members = public_members(AsyncRemoteSession)
    assert set(async_members) == set(sync_members)
    for name, async_member in async_members.items():
        sync_member = sync_members[name]
        if name == "page":
            assert isinstance(async_member, property) and inspect.iscoroutinefunction(async_member.fget)
            continue
        if isinstance(sync_member, property):
            assert isinstance(async_member, property), name
            assert inspect.signature(async_member.fget) == inspect.signature(sync_member.fget), name
            continue
        same_signature(sync_member, async_member)
    assert not hasattr(RemoteSession, "apage")
    assert not hasattr(RemoteSession, "await_for_auth")
    assert not hasattr(RemoteSession, "__aenter__")
    assert not hasattr(RemoteSession, "__aexit__")
    assert not hasattr(AsyncRemoteSession, "__enter__")
    assert not hasattr(AsyncRemoteSession, "__exit__")


def test_async_session_constructor_takes_the_sync_arguments() -> None:
    def parameters(init: Callable[..., Any]) -> list[tuple[str, Any, Any]]:
        return [(p.name, p.kind, p.default) for p in inspect.signature(init).parameters.values()]

    assert parameters(AsyncRemoteSession.__init__) == parameters(RemoteSession.__init__)
    sync_overloads = typing.get_overloads(RemoteSession.__init__)
    async_overloads = typing.get_overloads(AsyncRemoteSession.__init__)
    assert [parameters(o) for o in async_overloads] == [parameters(o) for o in sync_overloads]
    assert typing.get_type_hints(AsyncRemoteSession.__init__)["storage"] == AsyncRemoteFileStorage | None
    assert typing.get_type_hints(RemoteSession.__init__)["storage"] == RemoteFileStorage | None
    sync_session = NotteClient(api_key=KEY, server_url=SERVER).Session()
    client = AsyncNotteClient(api_key=KEY, server_url=SERVER)
    async_session = client.Session()
    assert isinstance(async_session, AsyncRemoteSession)
    attributes = {name for name in vars(sync_session) if not name.startswith("_")}
    assert {name for name in vars(async_session) if not name.startswith("_")} == attributes
    # The default storage is on the client's files, and unbound until the session starts.
    assert isinstance(async_session.storage, sessions.AsyncRemoteFileStorage)
    assert async_session.storage.client is client.files
    for session in (sync_session, async_session):
        with pytest.raises(ValueError, match="A session ID is required"):
            _ = session.storage.session_id


@pytest.mark.parametrize("sync,async_", [(SessionsClient, AsyncSessionsClient), (PageClient, AsyncPageClient)])
def test_async_clients_have_the_sync_handwritten_methods(sync: type, async_: type) -> None:
    def handwritten(cls: type) -> set[str]:
        return {
            name
            for base in cls.__mro__
            if base.__module__ in (sessions.__name__, PageClient.__module__)
            for name, value in vars(base).items()
            if not name.startswith("_") and inspect.isfunction(value)
        } - set(_RENAMED_METHODS.get(cls, {}))  # the deprecated 1.x aliases stay on the sync client

    assert handwritten(async_) == handwritten(sync)
    for name in handwritten(sync):
        same_signature(getattr(sync, name), getattr(async_, name))
    assert issubclass(async_, AsyncBaseClient) and issubclass(sync, BaseClient)


def test_async_client_sessions_have_a_page_client() -> None:
    client = AsyncNotteClient(api_key=KEY, server_url=SERVER)
    assert isinstance(client.sessions, AsyncSessionsClient)
    assert isinstance(client.sessions.page, AsyncPageClient)
    assert client.sessions.page.root_client is client
    assert inspect.signature(AsyncNotteClient.Session.fget).return_annotation == type[AsyncRemoteSession]


# ---------------------------------------------------------------------------
# Same requests: each scenario runs on `RemoteSession` and on `AsyncRemoteSession`

STAMP = utc_now()
GOTO = GotoAction(url="https://example.com")
CLICK = ClickAction(selector="#submit")


def executed(action: Any, *, success: bool = True, state: str | None = None, ran: bool | None = None) -> Any:
    captcha = CaptchaStatus(captcha_id="solve", page_id="page", generation=0, state=state) if state else None
    return ExecutionResultResponse(
        action=action,
        success=success,
        message="result",
        started_at=STAMP,
        ended_at=STAMP,
        action_executed=ran,
        captcha=captcha,
    ).model_dump(mode="json")


DEBUG = {
    "debug_url": "https://viewer.example/s-1",
    "ws": {"cdp": "wss://api.example/cdp", "recording": "wss://api.example/rec", "logs": "wss://api.example/logs"},
    "tabs": [],
}
TAB = {"metadata": {"tab_id": 0, "title": "t", "url": "https://example.com"}, "debug_url": "d", "ws_url": "w"}
CLOSED = {**SESSION, "status": "closed"}
STOP = ("DELETE", "/sessions/s-1/stop")
COOKIE = {"name": "a", "value": "b", "domain": "example.com", "path": "/", "httpOnly": False}


class Product(BaseModel):
    name: str


def router(routes: dict[tuple[str, str], list[tuple[int, Any]]]) -> Callable[[httpx.Request], httpx.Response]:
    """Answer each `(method, path)` with its responses in turn; the last one repeats."""
    queues = {key: list(answers) for key, answers in routes.items()}

    def handle(request: httpx.Request) -> httpx.Response:
        queue = queues[(request.method, request.url.path)]
        status, payload = queue.pop(0) if len(queue) > 1 else queue[0]
        return httpx.Response(status, content=json.dumps(payload).encode())

    return handle


class Awaiting:
    """A sync session whose methods return awaitables, so one async scenario drives both sessions."""

    def __init__(self, session: RemoteSession) -> None:
        self._session: RemoteSession = session

    def __getattr__(self, name: str) -> Callable[..., Awaitable[Any]]:
        method = getattr(self._session, name)

        async def call(*args: Any, **kwargs: Any) -> Any:
            return method(*args, **kwargs)

        return call


Scenario = Callable[[Any], Awaitable[Any]]


def same_on_both(
    monkeypatch: pytest.MonkeyPatch,
    routes: dict[tuple[str, str], list[tuple[int, Any]]],
    scenario: Scenario,
    *,
    max_retries: int = 0,
    clock_params: tuple[str, ...] = (),
    **options: Any,
) -> Any:
    """Run `scenario` on a sync and an async session; both must send, sleep and return the same.

    `clock_params` are query parameters computed from the wall clock, compared to the second.
    """
    expected = exchange_sync(
        monkeypatch,
        router(routes),
        lambda client: asyncio.run(scenario(Awaiting(client.Session(**options)))),
        max_retries=max_retries,
    )
    actual = asyncio.run(
        exchange_async(
            monkeypatch, router(routes), lambda client: scenario(client.Session(**options)), max_retries=max_retries
        )
    )
    for call in (*expected.calls, *actual.calls):
        for name in set(clock_params) & set(call.params):
            call.params[name] = str(round(float(call.params[name])))
    assert actual == expected
    return expected


SESSION_ROUTES: dict[tuple[str, str], list[tuple[int, Any]]] = {
    ("POST", "/sessions/start"): [(200, SESSION)],
    ("GET", "/sessions/s-1"): [(200, SESSION)],
    STOP: [(200, CLOSED)],
    ("POST", "/sessions/s-1/page/scrape"): [
        (200, {"markdown": "# page"}),
        (200, {"markdown": "", "structured": {"success": True, "data": {"name": "lamp"}}}),
        (200, {"markdown": "", "structured": {"success": False, "error": "nothing", "data": None}}),
    ],
    ("POST", "/sessions/s-1/page/observe"): [(200, Observation.empty().model_dump(mode="json"))],
    ("POST", "/sessions/s-1/page/execute"): [(200, executed(GOTO))],
    ("POST", "/sessions/s-1/cookies"): [(200, {"success": True, "message": "ok"})],
    ("GET", "/sessions/s-1/cookies"): [(200, {"cookies": [COOKIE]})],
    ("GET", "/sessions/s-1/offset"): [(200, {"offset": 3})],
    ("GET", "/sessions/s-1/debug"): [(200, DEBUG)],
    ("GET", "/sessions/s-1/debug/tab"): [(200, TAB)],
    ("POST", "/sessions/s-1/profile/save"): [(200, PROFILE)],
    ("GET", "/sessions/s-1/replay"): [(404, {"detail": "replay not found"}), (200, {"mp4_url": "https://cdn/r.mp4"})],
}


def test_session_lifecycle_sends_the_same_requests(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cookie_file = tmp_path / "cookies.json"
    _ = cookie_file.write_text(json.dumps([COOKIE]))

    async def scenario(session: Any) -> list[Any]:
        await session.start()
        results = [
            await session.status(),
            await session.scrape(only_main_content=False),
            await session.scrape(response_format=Product, instructions="the product"),
            await session.scrape(instructions="the product", raise_on_failure=False),
            await session.observe(),
            await session.execute(type="goto", url="https://example.com"),
            await session.execute(GOTO, raise_on_failure=False),
            await session.set_cookies(cookies=[COOKIE]),
            await session.set_cookies(cookie_file=cookie_file),
            await session.get_cookies(),
            await session.offset(),
            await session.debug_info(),
            await session.cdp_url(),
            await session.save_profile(name="github"),
        ]
        await session.stop()
        results.append(await session.replay(poll_interval=2))
        return results

    exchange = same_on_both(monkeypatch, SESSION_ROUTES, scenario, perception_type="fast")
    assert exchange.outcome[0] == "ok", exchange.outcome
    assert exchange.sleeps == [2]
    observe = next(call for call in exchange.calls if call.url.endswith("/page/observe"))
    assert json.loads(observe.data)["perception_type"] == "fast"
    assert [call.method for call in exchange.calls[-3:]] == ["DELETE", "GET", "GET"]
    assert exchange.calls[-3].params == {"close_reason": "manual"}


def test_sessions_client_methods_send_the_same_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario(session: Any) -> list[Any]:
        client = session.client if isinstance(session, AsyncRemoteSession) else Awaiting(session._session.client)
        return [
            await client.debug_tab_info("s-1", tab_idx=2),
            await client.debug_tab_info("s-1"),
            await client.stop("s-1", close_reason="error"),
            await client.replay("s-1", wait=False),
        ]

    exchange = same_on_both(monkeypatch, SESSION_ROUTES, scenario)
    assert [call.params for call in exchange.calls[:3]] == [{"tab_idx": "2"}, {}, {"close_reason": "error"}]


@pytest.mark.parametrize("status", [404, 500])
def test_errors_are_the_same(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    routes = {key: [(status, {"detail": "boom"})] for key in SESSION_ROUTES}

    async def scenario(session: Any) -> Any:
        return await session.start()

    exchange = same_on_both(monkeypatch, routes, scenario)
    assert exchange.outcome[0] == "error"


@pytest.mark.parametrize(
    "answer,outcome",
    [
        # already stopped: logged, not raised
        ((400, {"detail": "Session already stopped"}), ("ok", None)),
        ((200, SESSION), ("error", RuntimeError, "[Session] s-1 failed to stop")),
        ((500, {"detail": "down"}), "error"),
    ],
)
def test_stop_failures_are_the_same(monkeypatch: pytest.MonkeyPatch, answer: tuple[int, Any], outcome: Any) -> None:
    async def scenario(session: Any) -> None:
        await session.start()
        await session.stop()

    exchange = same_on_both(monkeypatch, {**SESSION_ROUTES, STOP: [answer]}, scenario)
    assert exchange.outcome == outcome if isinstance(outcome, tuple) else exchange.outcome[0] == outcome


def test_cookie_file_is_loaded_at_start_and_saved_at_stop(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    files = iter([tmp_path / "sync.json", tmp_path / "async.json"])
    for path in (tmp_path / "sync.json", tmp_path / "async.json"):
        _ = path.write_text(json.dumps([COOKIE]))

    async def scenario(session: Any) -> None:
        await session.start()
        await session.stop()

    routes = {**SESSION_ROUTES}
    expected = exchange_sync(
        monkeypatch,
        router(routes),
        lambda client: asyncio.run(scenario(Awaiting(client.Session(cookie_file=next(files))))),
    )
    actual = asyncio.run(
        exchange_async(monkeypatch, router(routes), lambda client: scenario(client.Session(cookie_file=next(files))))
    )
    assert actual == expected
    assert [call.method for call in expected.calls] == ["POST", "POST", "GET", "DELETE"]
    assert (tmp_path / "sync.json").read_text() == (tmp_path / "async.json").read_text()


@pytest.mark.parametrize("status", [529, 500])
def test_start_retries_are_the_same(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    # The API's error body carries its status, which the session's own retry reads.
    busy = {"status": status, "detail": "busy"}
    routes = {**SESSION_ROUTES, ("POST", "/sessions/start"): [(status, busy), (200, SESSION)]}

    async def scenario(session: Any) -> Any:
        await session.start()
        return session.session_id if isinstance(session, AsyncRemoteSession) else "s-1"

    exchange = same_on_both(monkeypatch, routes, scenario)
    assert [call.url for call in exchange.calls] == [f"{SERVER}/sessions/start"] * 2
    assert exchange.sleeps == ([sessions.CLUSTER_OVERLOAD_RETRY_DELAY] if status == 529 else [])


def test_authentication_wait_is_the_same(monkeypatch: pytest.MonkeyPatch) -> None:
    pending = {**SESSION, "status": "authenticating"}
    routes = {
        **SESSION_ROUTES,
        ("POST", "/sessions/start"): [(200, pending)],
        ("GET", "/sessions/s-1/auth"): [
            (200, {"session_id": "s-1", "status": "authenticating"}),
            (503, {"detail": "busy"}),
            (200, {"session_id": "s-1", "status": "authenticating"}),
            (200, {"session_id": "s-1", "status": "active"}),
        ],
    }

    async def scenario(session: Any) -> Any:
        await session.start()
        return await session.status()

    exchange = same_on_both(monkeypatch, routes, scenario)
    assert len(exchange.sleeps) == 3 and exchange.sleeps[1] == 1

    failed = {
        **routes,
        ("GET", "/sessions/s-1/auth"): [
            (200, {"session_id": "s-1", "status": "failed", "error": "Invalid credentials"})
        ],
    }
    exchange = same_on_both(monkeypatch, failed, scenario)
    assert exchange.outcome == ("error", RuntimeError, "Invalid credentials")
    assert exchange.calls[-1].params == {"close_reason": "error"}


def test_captcha_polling_is_the_same(monkeypatch: pytest.MonkeyPatch) -> None:
    routes = {
        **SESSION_ROUTES,
        ("POST", "/sessions/s-1/page/execute"): [
            (200, executed(CLICK, success=False, state="solving", ran=False)),
            (503, {"detail": "busy"}),
            (200, executed(CLICK, success=False, state="solving", ran=False)),
            (200, executed(CLICK, success=False, state="solved", ran=False)),
            (200, executed(CLICK)),
        ],
    }

    async def scenario(session: Any) -> Any:
        await session.start()
        return await session.execute(CLICK)

    exchange = same_on_both(monkeypatch, routes, scenario, clock_params=("captcha_timeout_seconds",))
    executes = [call for call in exchange.calls if call.url.endswith("/page/execute")]
    assert [json.loads(call.data)["type"] for call in executes] == ["click", *["captcha_solve"] * 3, "click"]
    assert executes[-1].params["target_page_id"] == "page"
    assert exchange.outcome[0] == "ok" and len(exchange.sleeps) == 3


@pytest.mark.parametrize("stopped", [True, False])
def test_replay_uses_known_stop_state_when_server_waits_for_close(
    monkeypatch: pytest.MonkeyPatch, stopped: bool
) -> None:
    async def scenario(session: AsyncRemoteSession):
        await session.start()
        if stopped:
            await session.stop()
        return await session.replay(poll_interval=2)

    routes = {
        **SESSION_ROUTES,
        ("GET", "/sessions/s-1/replay"): [
            (404, {"replay_status": "waiting_for_session", "retryable": False, "detail": "Close the session"}),
            (200, {"mp4_url": "https://cdn/r.mp4"}),
        ],
    }
    exchange = same_on_both(monkeypatch, routes, scenario)
    if stopped:
        assert exchange.outcome[0] == "ok"
        assert exchange.sleeps == [2]
    else:
        assert exchange.outcome[1] is ValueError
        assert exchange.sleeps == []


@pytest.mark.parametrize("state", ["closed", "resetting", "replaced"])
def test_replay_observes_stop_or_reset_during_request(monkeypatch: pytest.MonkeyPatch, state: str) -> None:
    session: RemoteSession | AsyncRemoteSession | None = None
    handle = router(SESSION_ROUTES)
    replay_calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal replay_calls
        if request.url.path.endswith("/replay"):
            replay_calls += 1
            if replay_calls == 1:
                assert session is not None and session.response is not None
                # Complete stop/reset state transitions while the old replay is in flight.
                if state == "resetting":
                    session.response = None
                elif state == "replaced":
                    session.response = session.response.model_copy(update={"session_id": "s-2", "status": "active"})
                else:
                    session.response = session.response.model_copy(update={"status": "closed"})
                return httpx.Response(404, json={"replay_status": "waiting_for_session", "retryable": False})
            return httpx.Response(200, json={"mp4_url": "https://cdn/r.mp4"})
        return handle(request)

    def sync_scenario(client: NotteClient):
        nonlocal session
        session = client.Session()
        session.start()
        return session.replay(poll_interval=2)

    async def async_scenario(client: AsyncNotteClient):
        nonlocal session
        session = client.Session()
        await session.start()
        return await session.replay(poll_interval=2)

    expected = exchange_sync(monkeypatch, respond, sync_scenario)
    replay_calls = 0
    actual = asyncio.run(exchange_async(monkeypatch, respond, async_scenario))
    assert actual == expected
    assert expected.outcome[0] == "ok"
    assert expected.sleeps == [2]
    replay_calls_seen = [call for call in expected.calls if call.url.endswith("/replay")]
    assert len(replay_calls_seen) == 2
    assert all(call.url.endswith("/sessions/s-1/replay") for call in replay_calls_seen)


def test_replay_waits_and_fails_the_same(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario(session: Any) -> Any:
        await session.start()
        # A timeout shorter than one poll interval: the first miss times out, whatever the clock says.
        return await session.replay(timeout=1, poll_interval=2)

    routes = {**SESSION_ROUTES, ("GET", "/sessions/s-1/replay"): [(404, {"detail": "replay not found"})]}
    exchange = same_on_both(monkeypatch, routes, scenario)
    assert exchange.outcome[1] is TimeoutError
    active = {**SESSION_ROUTES, ("GET", "/sessions/s-1/replay"): [(404, {"detail": "Session still active"})]}
    exchange = same_on_both(monkeypatch, active, scenario)
    assert exchange.outcome[1] is ValueError and exchange.sleeps == []


@pytest.mark.parametrize("failure", ["upload", "file"])
def test_entry_that_fails_after_creating_the_session_stops_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: str
) -> None:
    # The start creates the session, then fails loading its cookies: `async with` never runs the
    # body or `__aexit__`, so the entry itself must stop the session, on both sessions.
    routes = {**SESSION_ROUTES, ("POST", "/sessions/s-1/cookies"): [(400, {"detail": "bad cookie"})]}
    cookie_files = iter([tmp_path / "sync.json", tmp_path / "async.json"])
    for path in (tmp_path / "sync.json", tmp_path / "async.json"):
        _ = path.write_text(json.dumps([COOKIE]) if failure == "upload" else "not json")

    async def enter(session: Any) -> None:
        async with session:
            pytest.fail("the body must not run")

    def sync_enter(client: NotteClient) -> None:
        with client.Session(cookie_file=next(cookie_files)):
            pytest.fail("the body must not run")

    expected = exchange_sync(monkeypatch, router(routes), sync_enter)
    actual = asyncio.run(
        exchange_async(
            monkeypatch, router(routes), lambda client: enter(client.Session(cookie_file=next(cookie_files)))
        )
    )
    assert actual == expected
    assert expected.outcome[0] == "error"
    sent = [(call.method, call.url.removeprefix(SERVER)) for call in expected.calls]
    upload = [("POST", "/sessions/s-1/cookies")] if failure == "upload" else []
    # The stop saves the session's cookies to the cookie file first, as every stop does.
    assert sent == [("POST", "/sessions/start"), *upload, ("GET", "/sessions/s-1/cookies"), (STOP[0], STOP[1])]
    assert expected.calls[-1].params == {"close_reason": "error"}


@pytest.mark.parametrize("entry", ["sync with", "async with"])
def test_a_failed_browser_close_still_stops_the_playwright_driver(monkeypatch: pytest.MonkeyPatch, entry: str) -> None:
    # The browser fails to close: the local driver process is stopped anyway, then the session.
    asynchronous = entry != "sync with"
    browser = MagicMock()
    browser.close = (AsyncMock if asynchronous else MagicMock)(side_effect=RuntimeError("browser gone"))
    driver = MagicMock()
    driver.stop = AsyncMock() if asynchronous else MagicMock()

    def body(session: Any) -> None:
        prefix = "_async_playwright" if asynchronous else "_playwright"
        setattr(session, f"{prefix}_browser", browser)
        setattr(session, f"{prefix}_context", driver)

    def sync_with(client: NotteClient) -> None:
        with client.Session() as session:
            body(session)

    async def async_with(session: Any) -> None:
        async with session:
            body(session)

    if entry == "async with":
        exchange = asyncio.run(
            exchange_async(monkeypatch, router(SESSION_ROUTES), lambda client: async_with(client.Session()))
        )
    else:
        exchange = exchange_sync(monkeypatch, router(SESSION_ROUTES), sync_with)
    assert exchange.outcome[0] == "ok"
    driver.stop.assert_called_once_with()
    assert (exchange.calls[-1].method, exchange.calls[-1].url.removeprefix(SERVER)) == STOP


@pytest.mark.parametrize("entry", ["sync with", "async with"])
def test_a_dead_playwright_driver_does_not_skip_the_stop(monkeypatch: pytest.MonkeyPatch, entry: str) -> None:
    # Closing the local Playwright connection fails: the remote session is stopped anyway, and the
    # block's own exception is the one raised.
    dead = MagicMock()
    dead.close = (
        AsyncMock(side_effect=RuntimeError("driver died"))
        if entry != "sync with"
        else MagicMock(side_effect=RuntimeError("driver died"))
    )

    def body(session: Any) -> None:
        if entry == "sync with":
            session._playwright_browser = dead
        else:
            session._async_playwright_browser = dead
        raise ValueError("body failed")

    def sync_with(client: NotteClient) -> None:
        with client.Session() as session:
            body(session)

    async def async_with(session: Any) -> None:
        async with session:
            body(session)

    if entry == "async with":
        exchange = asyncio.run(
            exchange_async(monkeypatch, router(SESSION_ROUTES), lambda client: async_with(client.Session()))
        )
    else:
        exchange = exchange_sync(monkeypatch, router(SESSION_ROUTES), sync_with)
    assert exchange.outcome[:2] == ("error", ValueError)
    assert (exchange.calls[-1].method, exchange.calls[-1].url.removeprefix(SERVER)) == STOP
    assert exchange.calls[-1].params == {"close_reason": "error"}


@pytest.mark.parametrize("existing", ["attached", "started"])
def test_rejected_entry_does_not_stop_an_existing_session(monkeypatch: pytest.MonkeyPatch, existing: str) -> None:
    # Entering a session that is already attached or started is rejected by `start`; the browser
    # belongs to someone else (or to the earlier start), so the failed entry must not stop it.
    async def enter(session: Any, start: Callable[[], Awaitable[Any]]) -> None:
        if existing == "started":
            await start()
        async with session:
            pytest.fail("the body must not run")

    def sync_call(client: NotteClient) -> None:
        session = client.Session("s-1") if existing == "attached" else client.Session()

        if existing == "started":
            session.start()
        with session:
            pytest.fail("the body must not run")

    async def async_call(client: AsyncNotteClient) -> None:
        session = client.Session("s-1") if existing == "attached" else client.Session()
        await enter(session, session.start)

    expected = exchange_sync(monkeypatch, router(SESSION_ROUTES), sync_call)
    actual = asyncio.run(exchange_async(monkeypatch, router(SESSION_ROUTES), async_call))
    assert actual == expected
    assert expected.outcome == ("error", ValueError, "Session already started")
    sent = [(call.method, call.url.removeprefix(SERVER)) for call in expected.calls]
    assert sent == [("GET", "/sessions/s-1") if existing == "attached" else ("POST", "/sessions/start")]


def test_cancelled_exit_still_closes_playwright_and_stops_the_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Cancelling while `__aexit__` closes the Playwright browser must not cut the cleanup short:
    # the driver is still stopped and the remote session too, then the cancellation is raised.
    driver = MagicMock(stop=AsyncMock())

    async def scenario(session: Any) -> list[Any]:
        closing, release = asyncio.Event(), asyncio.Event()

        async def close() -> None:
            closing.set()
            await release.wait()

        browser = MagicMock(close=AsyncMock(side_effect=close))

        async def use() -> None:
            async with session:
                session._async_playwright_browser = browser
                session._async_playwright_context = driver

        task = asyncio.create_task(use())
        await closing.wait()
        for _ in range(3):
            _ = task.cancel()
            await asyncio.sleep(0)
        done_early = task.done()
        release.set()
        try:
            await task
            ending = "finished"
        except asyncio.CancelledError:
            ending = "cancelled"
        return [done_early, ending]

    exchange = asyncio.run(
        exchange_async(monkeypatch, router(SESSION_ROUTES), lambda client: scenario(client.Session()))
    )
    assert exchange.outcome == ("ok", [False, "cancelled"])
    driver.stop.assert_awaited_once_with()
    assert (exchange.calls[-1].method, exchange.calls[-1].url.removeprefix(SERVER)) == STOP
    assert exchange.calls[-1].params == {"close_reason": "manual"}


def test_failed_authentication_in_async_with_sends_exactly_one_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    routes = {
        **SESSION_ROUTES,
        ("POST", "/sessions/start"): [(200, {**SESSION, "status": "authenticating"})],
        ("GET", "/sessions/s-1/auth"): [(200, {"session_id": "s-1", "status": "failed", "error": "Login failed"})],
    }

    async def enter(session: Any) -> None:
        async with session:
            pytest.fail("the body must not run")

    def sync_enter(client: NotteClient) -> None:
        with client.Session():
            pytest.fail("the body must not run")

    expected = exchange_sync(monkeypatch, router(routes), sync_enter)
    actual = asyncio.run(exchange_async(monkeypatch, router(routes), lambda client: enter(client.Session())))
    assert actual == expected
    assert expected.outcome == ("error", RuntimeError, "Login failed")
    stops = [call for call in expected.calls if (call.method, call.url.removeprefix(SERVER)) == STOP]
    assert len(stops) == 1 and stops[0].params == {"close_reason": "error"}


@pytest.mark.parametrize("asynchronous", [False, True])
def test_entry_does_not_stop_a_session_its_start_already_closed(asynchronous: bool) -> None:
    # `start` closed the session it created before failing (as a failed authentication wait
    # does): the entry sends no second stop, like `RemoteSession.__enter__`.
    if asynchronous:
        session: Any = AsyncNotteClient(api_key=KEY, server_url=SERVER).Session()
    else:
        session = NotteClient(api_key=KEY, server_url=SERVER).Session()

    def start(**_: Any) -> None:
        session.response = SimpleNamespace(session_id="s-1", status="closed")
        raise RuntimeError("Login failed")

    session.start = AsyncMock(side_effect=start) if asynchronous else MagicMock(side_effect=start)
    session.stop = AsyncMock() if asynchronous else MagicMock()

    async def enter() -> None:
        async with session:
            pytest.fail("the body must not run")

    with pytest.raises(RuntimeError, match="Login failed"):
        if asynchronous:
            asyncio.run(enter())
        else:
            with session:
                pytest.fail("the body must not run")
    session.start.assert_called_once_with(**({"wait_for_authentication": False} if asynchronous else {}))
    session.stop.assert_not_called()


def test_reset_stops_the_session_and_starts_a_new_one(monkeypatch: pytest.MonkeyPatch) -> None:
    second = {**SESSION, "session_id": "s-2"}
    routes = {
        **SESSION_ROUTES,
        ("POST", "/sessions/start"): [(200, SESSION), (200, second)],
        ("GET", "/sessions/s-2"): [(200, second)],
    }

    async def scenario(session: Any) -> Any:
        await session.start()
        await session.reset()
        return await session.status()

    exchange = same_on_both(monkeypatch, routes, scenario)
    sent = [(call.method, call.url.removeprefix(SERVER)) for call in exchange.calls]
    assert sent == [("POST", "/sessions/start"), STOP, ("POST", "/sessions/start"), ("GET", "/sessions/s-2")]
    assert exchange.outcome == ("ok", {**exchange.outcome[1], "session_id": "s-2"})


def unwrapped(session: Any) -> RemoteSession | AsyncRemoteSession:
    """The session behind a scenario's argument, to read its attributes."""
    return session._session if isinstance(session, Awaiting) else session


def test_start_and_reset_bind_the_storage_to_the_session(monkeypatch: pytest.MonkeyPatch) -> None:
    second = {**SESSION, "session_id": "s-2"}
    routes = {**SESSION_ROUTES, ("POST", "/sessions/start"): [(200, SESSION), (200, second)]}

    async def scenario(session: Any) -> list[Any]:
        storage = unwrapped(session).storage
        await session.start()
        # An unbound storage is bound in place; one bound to the stopped session is replaced.
        started = unwrapped(session).storage
        await session.reset()
        reset = unwrapped(session).storage
        return [
            started is storage,
            started.session_id,
            reset is started,
            reset.session_id,
            reset.client is storage.client,
        ]

    exchange = same_on_both(monkeypatch, routes, scenario)
    assert exchange.outcome == ("ok", [True, "s-1", False, "s-2", True])


def test_attached_session_storage_is_bound_to_its_id(monkeypatch: pytest.MonkeyPatch) -> None:
    async def attach(client: AsyncNotteClient) -> str:
        return client.Session("s-1").storage.session_id

    sync = exchange_sync(monkeypatch, router(SESSION_ROUTES), lambda client: client.Session("s-1").storage.session_id)
    async_ = asyncio.run(exchange_async(monkeypatch, router(SESSION_ROUTES), attach))
    assert sync.outcome == async_.outcome == ("ok", "s-1")
    # The async constructor reads no status: the storage is bound without a request.
    assert not async_.calls


def test_session_uses_the_storage_it_is_given(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario(session: Any) -> list[Any]:
        given = unwrapped(session).storage
        await session.start()
        return [unwrapped(session).storage is given, given.session_id]

    def run(client: NotteClient | AsyncNotteClient, storage_id: str | None) -> Any:
        session = client.Session(storage=client.FileStorage(storage_id))
        return scenario(session if isinstance(session, AsyncRemoteSession) else Awaiting(session))

    for storage_id, expected in [(None, [True, "s-1"]), ("s-9", [False, "s-9"])]:
        sync = exchange_sync(monkeypatch, router(SESSION_ROUTES), lambda c: asyncio.run(run(c, storage_id)))
        assert asyncio.run(exchange_async(monkeypatch, router(SESSION_ROUTES), lambda c: run(c, storage_id))) == sync
        assert sync.outcome == ("ok", expected)


@pytest.mark.asyncio
async def test_session_storage_uploads_and_downloads_with_the_same_requests(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    upload = tmp_path / "notes.txt"
    _ = upload.write_text("upload-data")
    routes = {
        **file_routes([[file_entry("file-1"), file_entry("file-2", "second.txt", "session_download")]]),
        ("POST", "/sessions/start"): SESSION,
        ("DELETE", "/sessions/s-1/stop"): CLOSED,
    }

    async def flow(client: Any, wait: Callable[[Any], Awaitable[Any]]) -> list[Any]:
        session = client.Session()
        await wait(session.start())
        uploaded = await wait(session.storage.upload(str(upload), "renamed.txt"))
        listed = await wait(session.storage.list())
        path = await wait(session.storage.download("file-2", str(tmp_path / "out"), force=True))
        await wait(session.stop())
        return [uploaded, listed, Path(path).name, Path(path).read_text()]

    exchange = await same_exchange(monkeypatch, routes, flow)
    assert exchange.outcome[0] == "ok", exchange.outcome
    assert exchange.outcome[1][2:] == ["second.txt", "hello"]
    sent = [(call.method, call.url.removeprefix(SERVER).split("?")[0]) for call in exchange.calls]
    assert sent == [
        ("POST", "/sessions/start"),
        ("POST", "/sessions/s-1/files"),
        ("GET", "/sessions/s-1/files"),
        ("GET", "/sessions/s-1/files"),
        ("GET", "/sessions/s-1/files/file-2"),
        STOP,
    ]
    assert exchange.calls[1].files == {"file": ("renamed.txt", b"upload-data", "text/plain")}


# ---------------------------------------------------------------------------
# Async behavior: cancellation, concurrency, no blocking I/O on the event loop


class Api:
    """An async fake API for `AsyncNotteClient` whose routes can hold a request until released."""

    def __init__(self, routes: dict[tuple[str, str], list[tuple[int, Any]]]) -> None:
        self.handle: Callable[[httpx.Request], httpx.Response] = router(routes)
        self.requests: list[httpx.Request] = []
        self.held: dict[tuple[str, str], asyncio.Event] = {}
        self.arrived: dict[tuple[str, str], asyncio.Event] = {}
        # Requests answered: a request cancelled while held never gets here.
        self.answered: list[tuple[str, str]] = []

    def hold(self, method: str, path: str) -> asyncio.Event:
        self.arrived[(method, path)] = asyncio.Event()
        release = self.held[(method, path)] = asyncio.Event()
        return release

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.method, request.url.path)
        if key in self.held:
            self.arrived[key].set()
            await self.held[key].wait()
        self.answered.append(key)
        return self.handle(request)

    def sent(self) -> list[tuple[str, str]]:
        return [(request.method, request.url.path) for request in self.requests]


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Api]:
    def install(routes: dict[tuple[str, str], list[tuple[int, Any]]] = SESSION_ROUTES) -> Api:
        fake = Api(routes)
        client = async_http_client()
        client._transport = httpx.MockTransport(fake)
        monkeypatch.setattr(AsyncSharedHttpClient, "get", lambda _: client)
        return fake

    return install


@pytest.mark.asyncio
async def test_async_with_starts_and_stops(api: Callable[..., Api]) -> None:
    fake = api()
    client = AsyncNotteClient(api_key=KEY, server_url=SERVER)
    async with client.Session() as session:
        assert session.session_id == "s-1"
        assert await session.scrape() == "# page"
    assert fake.sent() == [("POST", "/sessions/start"), ("POST", "/sessions/s-1/page/scrape"), STOP]
    assert fake.requests[-1].url.params["close_reason"] == "manual"


@pytest.mark.asyncio
async def test_exception_in_async_with_stops_as_error(api: Callable[..., Api]) -> None:
    fake = api({**SESSION_ROUTES, STOP: [(500, {"detail": "down"})]})
    client = AsyncNotteClient(api_key=KEY, server_url=SERVER, max_retries=0)
    with pytest.raises(LookupError, match="body failed"):
        async with client.Session():
            raise LookupError("body failed")
    # The stop failed too: logged, and the body's exception is the one raised.
    assert fake.sent()[-1] == STOP
    assert fake.requests[-1].url.params["close_reason"] == "error"


@pytest.mark.asyncio
async def test_cancelled_entry_stops_the_session_its_start_creates(api: Callable[..., Api]) -> None:
    fake = api()
    release = fake.hold("POST", "/sessions/start")
    client = AsyncNotteClient(api_key=KEY, server_url=SERVER)

    async def enter() -> None:
        async with client.Session():
            pytest.fail("the body must not run")

    task = asyncio.create_task(enter())
    await fake.arrived[("POST", "/sessions/start")].wait()
    _ = task.cancel()
    await asyncio.sleep(0)
    # The cancelled entry still waits for the start it shielded, then stops what it created.
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert fake.sent() == [("POST", "/sessions/start"), STOP]
    assert fake.requests[-1].url.params["close_reason"] == "error"


@pytest.mark.asyncio
async def test_repeated_cancellation_still_stops_the_session_its_start_creates(api: Callable[..., Api]) -> None:
    fake = api()
    release = fake.hold("POST", "/sessions/start")
    client = AsyncNotteClient(api_key=KEY, server_url=SERVER)

    async def enter() -> None:
        async with client.Session():
            pytest.fail("the body must not run")

    task = asyncio.create_task(enter())
    await fake.arrived[("POST", "/sessions/start")].wait()
    for _ in range(3):
        _ = task.cancel()
        await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert fake.sent() == [("POST", "/sessions/start"), STOP]


@pytest.mark.asyncio
async def test_cancellation_during_the_cleanup_stop_does_not_abandon_it(api: Callable[..., Api]) -> None:
    fake = api()
    release_start = fake.hold("POST", "/sessions/start")
    release_stop = fake.hold(*STOP)
    client = AsyncNotteClient(api_key=KEY, server_url=SERVER)

    async def enter() -> None:
        async with client.Session():
            pytest.fail("the body must not run")

    task = asyncio.create_task(enter())
    await fake.arrived[("POST", "/sessions/start")].wait()
    _ = task.cancel()
    await asyncio.sleep(0)
    release_start.set()
    await fake.arrived[STOP].wait()
    # Cancelling again while the cleanup's stop request is in flight must not cut it short.
    for _ in range(3):
        _ = task.cancel()
        await asyncio.sleep(0)
    assert not task.done()
    release_stop.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert fake.answered == [("POST", "/sessions/start"), STOP]


@pytest.mark.asyncio
async def test_cancelled_exit_does_not_abandon_the_stop_request(api: Callable[..., Api]) -> None:
    fake = api()
    release = fake.hold(*STOP)
    client = AsyncNotteClient(api_key=KEY, server_url=SERVER)

    async def use() -> None:
        async with client.Session():
            pass

    task = asyncio.create_task(use())
    await fake.arrived[STOP].wait()
    for _ in range(3):
        _ = task.cancel()
        await asyncio.sleep(0)
    assert not task.done()
    release.set()
    # The cleanup finished; the cancellation is raised afterwards.
    with pytest.raises(asyncio.CancelledError):
        await task
    assert fake.answered == [("POST", "/sessions/start"), STOP]


@pytest.mark.asyncio
async def test_cancelled_authentication_wait_stops_the_session(api: Callable[..., Api]) -> None:
    fake = api(
        {
            **SESSION_ROUTES,
            ("POST", "/sessions/start"): [(200, {**SESSION, "status": "authenticating"})],
            ("GET", "/sessions/s-1/auth"): [(200, {"session_id": "s-1", "status": "authenticating"})],
        }
    )
    _ = fake.hold("GET", "/sessions/s-1/auth")
    client = AsyncNotteClient(api_key=KEY, server_url=SERVER)

    async def enter() -> None:
        async with client.Session():
            pytest.fail("the body must not run")

    task = asyncio.create_task(enter())
    await fake.arrived[("GET", "/sessions/s-1/auth")].wait()
    _ = task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert fake.sent() == [("POST", "/sessions/start"), ("GET", "/sessions/s-1/auth"), STOP]
    assert fake.requests[-1].url.params["close_reason"] == "error"


@pytest.mark.asyncio
async def test_failed_start_in_async_with_sends_no_stop(api: Callable[..., Api]) -> None:
    fake = api({**SESSION_ROUTES, ("POST", "/sessions/start"): [(400, {"detail": "bad request"})]})
    client = AsyncNotteClient(api_key=KEY, server_url=SERVER)
    with pytest.raises(Exception, match="bad request"):
        async with client.Session():
            pytest.fail("the body must not run")
    assert fake.sent() == [("POST", "/sessions/start")]


@pytest.mark.asyncio
async def test_sessions_run_concurrently(api: Callable[..., Api]) -> None:
    fake = api({**SESSION_ROUTES, ("POST", "/sessions/s-1/page/scrape"): [(200, {"markdown": "# page"})]})
    release = fake.hold("POST", "/sessions/s-1/page/scrape")
    client = AsyncNotteClient(api_key=KEY, server_url=SERVER)
    in_flight = 0

    async def scrape() -> str:
        nonlocal in_flight
        async with client.Session() as session:
            in_flight += 1
            if in_flight == 2:
                release.set()
            return await session.scrape()

    # Both scrapes wait until both sessions are open: sequential sessions would never finish.
    results = await asyncio.wait_for(asyncio.gather(scrape(), scrape()), timeout=5)
    assert results == ["# page", "# page"]
    assert fake.sent().count(STOP) == 2


@pytest.mark.asyncio
async def test_attached_session_reads_its_state_on_first_use(api: Callable[..., Api]) -> None:
    fake = api()
    session = AsyncNotteClient(api_key=KEY, server_url=SERVER).Session("s-1")
    assert session.session_id == "s-1" and fake.sent() == []
    with pytest.raises(ValueError, match="already started"):
        await session.start()
    assert fake.sent() == [("GET", "/sessions/s-1")]
    assert session.response is not None and session.response.status == "active"
    assert await session.cdp_url() == "wss://api.example/cdp"


@pytest.mark.asyncio
async def test_unstarted_session_raises_like_the_sync_one(api: Callable[..., Api]) -> None:
    fake = api()
    session = AsyncNotteClient(api_key=KEY, server_url=SERVER).Session()
    with pytest.raises(ValueError, match="start the session first"):
        _ = session.session_id
    with pytest.raises(ValueError, match="start the session first to get the cdp url"):
        _ = await session.cdp_url()
    with pytest.raises(ValueError, match="has not started"):
        await session.wait_for_auth()
    assert fake.sent() == []


@pytest.mark.asyncio
async def test_local_files_are_read_and_written_off_the_event_loop(
    api: Callable[..., Api], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _ = api()
    loop_thread = threading.get_ident()
    threads: list[str] = []
    read = sessions.SetCookiesRequest.from_json
    write = sessions.create_or_append_cookies_to_file

    def reading(path: Any) -> Any:
        threads.append("read-loop" if threading.get_ident() == loop_thread else "read-thread")
        return read(path)

    def writing(path: Any, cookies: Any) -> None:
        threads.append("write-loop" if threading.get_ident() == loop_thread else "write-thread")
        write(path, cookies)

    monkeypatch.setattr(sessions.SetCookiesRequest, "from_json", staticmethod(reading))
    monkeypatch.setattr(sessions, "create_or_append_cookies_to_file", writing)
    cookie_file = tmp_path / "cookies.json"
    _ = cookie_file.write_text(json.dumps([COOKIE]))
    async with AsyncNotteClient(api_key=KEY, server_url=SERVER).Session(cookie_file=cookie_file):
        pass
    assert threads == ["read-thread", "write-thread"]


@pytest.mark.asyncio
async def test_viewers_open_the_browser_off_the_event_loop(
    api: Callable[..., Api], monkeypatch: pytest.MonkeyPatch
) -> None:
    viewer_url = "https://viewer.example/live/s-1"
    fake = api({**SESSION_ROUTES, ("GET", "/sessions/s-1"): [(200, {**SESSION, "viewer_url": viewer_url})]})
    loop_thread = threading.get_ident()
    opened: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        sessions, "open_browser", lambda url, new=0: opened.append((url, threading.get_ident() != loop_thread))
    )
    client = AsyncNotteClient(api_key=KEY, server_url=SERVER)
    async with client.Session() as session:
        await session.viewer_cdp()
        await session.viewer()
        service = await session.viewer_notebook()
    assert opened == [(DEBUG["debug_url"], True), (viewer_url, True)]
    assert service.wss_url == DEBUG["ws"]["recording"]
    # `viewer` opens the browser viewer: the session has no viewer url, so it is read first.
    assert ("GET", "/sessions/s-1") in fake.sent()


@pytest.mark.asyncio
async def test_page_is_the_async_playwright_page_and_closes_with_the_session(
    api: Callable[..., Api], monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = api()
    page = MagicMock()
    context = MagicMock(pages=[page])
    browser = MagicMock(contexts=[context], close=AsyncMock())
    playwright = MagicMock(stop=AsyncMock())
    playwright.chromium.connect_over_cdp = AsyncMock(return_value=browser)
    starter = MagicMock(start=AsyncMock(return_value=playwright))
    monkeypatch.setattr(sessions, "_async_playwright_available", True)
    monkeypatch.setattr(sessions, "_async_playwright", MagicMock(return_value=starter))
    async with AsyncNotteClient(api_key=KEY, server_url=SERVER).Session() as session:
        assert await session.page is page
        assert await session.page is page
    playwright.chromium.connect_over_cdp.assert_awaited_once()
    assert playwright.chromium.connect_over_cdp.await_args.args == ("wss://api.example/cdp",)
    context.on.assert_called_once_with("dialog", sessions._observe_server_owned_dialog)
    browser.close.assert_awaited_once()
    playwright.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_observe_deprecation_points_at_the_caller(api: Callable[..., Api]) -> None:
    _ = api()
    async with AsyncNotteClient(api_key=KEY, server_url=SERVER).Session() as session:
        with pytest.warns(DeprecationWarning, match="instructions") as caught:
            actions = await session.observe(instructions="the buttons")
    assert actions == []
    assert caught[0].filename == __file__


# ---------------------------------------------------------------------------
# `AsyncBaseClient._request_file`


@pytest.mark.parametrize(
    "answer,output",
    [
        ((200, b"\x00mp4"), "replay.mp4"),
        # An MP4 whose bytes are not valid UTF-8: `json()` raises `UnicodeDecodeError`, not a JSON error.
        ((200, b"\x00\x00\x00\x18ftypmp42\x80\x81"), "replay.mp4"),
        ((200, b"\x00mp4"), "replay.txt"),
        ((404, b'{"detail": "missing"}'), None),
    ],
)
def test_request_file_is_the_same(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, answer: tuple[int, bytes], output: str | None
) -> None:
    endpoint = NotteEndpoint(path="{session_id}/replay".format(session_id="s-1"), response=BaseModel, method="GET")

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(answer[0], content=answer[1])

    def path(name: str) -> str | None:
        return str(tmp_path / name / output) if output else None

    (tmp_path / "sync").mkdir()
    (tmp_path / "async").mkdir()
    expected = exchange_sync(
        monkeypatch, handle, lambda client: client.sessions._request_file(endpoint, "mp4", path("sync"))
    )
    actual = asyncio.run(
        exchange_async(
            monkeypatch, handle, lambda client: client.sessions._request_file(endpoint, "mp4", path("async"))
        )
    )
    assert actual == expected
    # A file answer with a `.mp4` destination downloads; a JSON error or a wrong extension raises.
    assert expected.outcome[0] == ("ok" if answer[0] == 200 and output == "replay.mp4" else "error"), expected.outcome
    if expected.outcome[0] == "ok" and output:
        assert (tmp_path / "async" / output).read_bytes() == (tmp_path / "sync" / output).read_bytes() == answer[1]


@pytest.mark.parametrize("retryable", [True, False])
def test_disabled_replay_never_polls_on_sync_or_async_client(monkeypatch: pytest.MonkeyPatch, retryable: bool) -> None:
    async def scenario(session):
        await session.start()
        await session.stop()
        return await session.replay(poll_interval=2)

    routes = {
        **SESSION_ROUTES,
        ("GET", "/sessions/s-1/replay"): [
            (
                404,
                {
                    "replay_status": "disabled",
                    "retryable": retryable,
                    "message": "Session recording was disabled at creation",
                },
            )
        ],
    }
    exchange = same_on_both(monkeypatch, routes, scenario)
    assert exchange.outcome[1] is NotteAPIError
    assert exchange.sleeps == []
    assert len([call for call in exchange.calls if call.url.endswith("/replay")]) == 1
