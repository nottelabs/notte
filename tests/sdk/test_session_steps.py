"""Session steps, page by page: `GET /sessions/{session_id}/steps?cursor=...&limit=...`.

Each scenario runs through `NotteClient` and `AsyncNotteClient` (`assert_same_exchange`), on the
sessions resource and on a session object, and must send the same requests and return the same steps.
"""

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from notte_sdk import AsyncNotteClient, NotteClient
from notte_sdk.endpoints.sessions import AsyncRemoteSession, RemoteSession
from notte_sdk.errors import NotteAPIError
from notte_sdk.types import SessionResponse, SessionStepsResponse

from tests.sdk.test_async_resources import SESSION, Exchange, assert_same_exchange, collect
from tests.sdk.test_generated_endpoints import SERVER

STEPS_URL = f"{SERVER}/sessions/s-1/steps"
# Opaque: characters that need URL encoding must come back to the API unchanged.
CURSOR_2 = "c2+/=&x"
CURSOR_3 = "c3"
STEP = {"type": "execution_result", "value": {"action": {"type": "goto", "url": "https://example.com"}}}
PAGES: dict[str | None, dict[str, Any]] = {
    None: {"steps": [{**STEP, "n": 1}, {**STEP, "n": 2}], "next_cursor": CURSOR_2},
    CURSOR_2: {"steps": [{**STEP, "n": 3}], "next_cursor": CURSOR_3},
    CURSOR_3: {"steps": [{**STEP, "n": 4}], "next_cursor": None},
}


def pages(
    by_cursor: dict[str | None, dict[str, Any]], expired: frozenset[str] = frozenset()
) -> Callable[[httpx.Request], httpx.Response]:
    """The API: the page of the request's cursor, or a 400 for an expired cursor."""

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET" and str(request.url.copy_with(query=None)) == STEPS_URL
        cursor = request.url.params.get("cursor")
        if cursor in expired:
            return httpx.Response(400, json={"detail": "Invalid or expired cursor"})
        return httpx.Response(200, json=by_cursor[cursor])

    return handle


def started(client: NotteClient | AsyncNotteClient) -> RemoteSession | AsyncRemoteSession:
    """A session object bound to session `s-1`, without starting it."""
    session = client.Session()
    session.response = SessionResponse.model_validate(SESSION)
    return session


def numbers(exchange: Exchange) -> list[int]:
    assert exchange.outcome[0] == "ok", exchange.outcome
    return [step["n"] for step in exchange.outcome[1]]


def queries(exchange: Exchange) -> list[dict[str, Any]]:
    return [call.params for call in exchange.calls]


# ---------------------------------------------------------------------------
# One page


@pytest.mark.asyncio
async def test_one_page(monkeypatch: pytest.MonkeyPatch) -> None:
    exchange = await assert_same_exchange(monkeypatch, pages(PAGES), lambda c: c.sessions.steps("s-1"))
    assert exchange.outcome == ("ok", {"steps": PAGES[None]["steps"], "next_cursor": CURSOR_2})
    # No cursor and no limit: the API's first page with its default size.
    assert queries(exchange) == [{}]


@pytest.mark.asyncio
async def test_next_page_sends_the_cursor_back_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    exchange = await assert_same_exchange(
        monkeypatch, pages(PAGES), lambda c: c.sessions.steps("s-1", cursor=CURSOR_2, limit=1)
    )
    assert exchange.outcome == ("ok", PAGES[CURSOR_2])
    assert queries(exchange) == [{"cursor": CURSOR_2, "limit": "1"}]


def test_page_is_the_session_steps_model(monkeypatch: pytest.MonkeyPatch) -> None:
    handle = pages(PAGES)
    client = NotteClient(api_key="test-api-key", server_url=SERVER)  # pragma: allowlist secret
    http = httpx.Client(transport=httpx.MockTransport(handle))
    monkeypatch.setattr("notte_sdk._transport.SharedHttpClient.get", lambda _: http)
    page = client.sessions.steps("s-1")
    assert isinstance(page, SessionStepsResponse)
    assert page.steps == PAGES[None]["steps"] and page.next_cursor == CURSOR_2


# ---------------------------------------------------------------------------
# Several pages


@pytest.mark.asyncio
async def test_iter_steps_follows_next_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    exchange = await assert_same_exchange(monkeypatch, pages(PAGES), lambda c: collect(c.sessions.iter_steps("s-1")))
    assert numbers(exchange) == [1, 2, 3, 4]
    assert queries(exchange) == [{}, {"cursor": CURSOR_2}, {"cursor": CURSOR_3}]


@pytest.mark.asyncio
async def test_session_object_iterates_and_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    exchange = await assert_same_exchange(monkeypatch, pages(PAGES), lambda c: collect(started(c).iter_steps(limit=2)))
    assert numbers(exchange) == [1, 2, 3, 4]
    assert queries(exchange) == [{"limit": "2"}, {"cursor": CURSOR_2, "limit": "2"}, {"cursor": CURSOR_3, "limit": "2"}]

    exchange = await assert_same_exchange(monkeypatch, pages(PAGES), lambda c: started(c).steps(cursor=CURSOR_3))
    assert exchange.outcome == ("ok", PAGES[CURSOR_3])
    assert queries(exchange) == [{"cursor": CURSOR_3}]


def test_iter_steps_reads_pages_as_it_goes(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[httpx.Request] = []
    handle = pages(PAGES)

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handle(request)

    http = httpx.Client(transport=httpx.MockTransport(record))
    monkeypatch.setattr("notte_sdk._transport.SharedHttpClient.get", lambda _: http)
    steps = NotteClient(api_key="test-api-key", server_url=SERVER).sessions.iter_steps(
        "s-1"
    )  # pragma: allowlist secret
    assert seen == []
    assert next(steps)["n"] == 1 and next(steps)["n"] == 2
    assert len(seen) == 1
    assert next(steps)["n"] == 3
    assert len(seen) == 2


# ---------------------------------------------------------------------------
# Empty


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"steps": [], "next_cursor": None}, {}], ids=["explicit", "defaults"])
async def test_empty(monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]) -> None:
    exchange = await assert_same_exchange(
        monkeypatch, pages({None: payload}), lambda c: collect(c.sessions.iter_steps("s-1"))
    )
    assert exchange.outcome == ("ok", [])
    assert queries(exchange) == [{}]

    exchange = await assert_same_exchange(monkeypatch, pages({None: payload}), lambda c: c.sessions.steps("s-1"))
    assert exchange.outcome == ("ok", {"steps": [], "next_cursor": None})


@pytest.mark.asyncio
async def test_empty_page_with_a_cursor_continues(monkeypatch: pytest.MonkeyPatch) -> None:
    by_cursor = {None: {"steps": [], "next_cursor": "more"}, "more": {"steps": [{**STEP, "n": 1}], "next_cursor": None}}
    exchange = await assert_same_exchange(
        monkeypatch, pages(by_cursor), lambda c: collect(c.sessions.iter_steps("s-1"))
    )
    assert numbers(exchange) == [1]
    assert queries(exchange) == [{}, {"cursor": "more"}]


# ---------------------------------------------------------------------------
# Limit


@pytest.mark.asyncio
async def test_limit_is_sent_on_every_page(monkeypatch: pytest.MonkeyPatch) -> None:
    exchange = await assert_same_exchange(monkeypatch, pages(PAGES), lambda c: c.sessions.steps("s-1", limit=7))
    assert queries(exchange) == [{"limit": "7"}]

    exchange = await assert_same_exchange(
        monkeypatch, pages(PAGES), lambda c: collect(c.sessions.iter_steps("s-1", limit=7))
    )
    assert queries(exchange) == [{"limit": "7"}, {"cursor": CURSOR_2, "limit": "7"}, {"cursor": CURSOR_3, "limit": "7"}]


# ---------------------------------------------------------------------------
# A cursor that is no longer valid: 400, restart from the first page


@pytest.mark.asyncio
async def test_expired_cursor_raises_400(monkeypatch: pytest.MonkeyPatch) -> None:
    exchange = await assert_same_exchange(
        monkeypatch, pages(PAGES, expired=frozenset({CURSOR_2})), lambda c: c.sessions.steps("s-1", cursor=CURSOR_2)
    )
    assert exchange.outcome[:2] == ("error", NotteAPIError)
    assert "400" in exchange.outcome[2]

    # The iterator does not restart on its own (that would yield the first steps again): it raises.
    exchange = await assert_same_exchange(
        monkeypatch, pages(PAGES, expired=frozenset({CURSOR_2})), lambda c: collect(c.sessions.iter_steps("s-1"))
    )
    assert exchange.outcome[:2] == ("error", NotteAPIError)
    assert queries(exchange) == [{}, {"cursor": CURSOR_2}]


def test_restart_after_400_reads_from_the_first_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """The documented recovery: catch the 400, then start a new iteration (no cursor)."""
    expired: set[str] = {CURSOR_2}
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        cursor = request.url.params.get("cursor")
        if cursor in expired:
            return httpx.Response(400, json={"detail": "Invalid or expired cursor"})
        return httpx.Response(200, json=PAGES[cursor])

    http = httpx.Client(transport=httpx.MockTransport(handle))
    monkeypatch.setattr("notte_sdk._transport.SharedHttpClient.get", lambda _: http)
    client = NotteClient(api_key="test-api-key", server_url=SERVER)  # pragma: allowlist secret

    got: list[int] = []
    with pytest.raises(NotteAPIError) as error:
        for step in client.sessions.iter_steps("s-1"):
            got.append(step["n"])
    assert error.value.status_code == 400
    assert got == [1, 2]

    expired.clear()
    assert [step["n"] for step in client.sessions.iter_steps("s-1")] == [1, 2, 3, 4]
    assert [request.url.params.get("cursor") for request in seen] == [None, CURSOR_2, None, CURSOR_2, CURSOR_3]


@pytest.mark.asyncio
async def test_async_restart_after_400_reads_from_the_first_page(monkeypatch: pytest.MonkeyPatch) -> None:
    expired: set[str] = {CURSOR_2}

    def handle(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("cursor")
        if cursor in expired:
            return httpx.Response(400, json={"detail": "Invalid or expired cursor"})
        return httpx.Response(200, json=PAGES[cursor])

    http = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr("notte_sdk._transport.AsyncSharedHttpClient.get", lambda _: http)
    session = started(AsyncNotteClient(api_key="test-api-key", server_url=SERVER))  # pragma: allowlist secret
    assert isinstance(session, AsyncRemoteSession)

    got: list[int] = []
    with pytest.raises(NotteAPIError) as error:
        async for step in session.iter_steps():
            got.append(step["n"])
    assert error.value.status_code == 400
    assert got == [1, 2]

    expired.clear()
    assert [step["n"] async for step in session.iter_steps()] == [1, 2, 3, 4]
    await http.aclose()


# ---------------------------------------------------------------------------
# The status response keeps its steps


@pytest.mark.asyncio
async def test_status_still_returns_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    status = {**SESSION, "steps": [STEP]}

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=status)

    exchange = await assert_same_exchange(monkeypatch, handle, lambda c: c.sessions.status("s-1"))
    assert exchange.outcome[0] == "ok" and exchange.outcome[1]["steps"] == [STEP]
