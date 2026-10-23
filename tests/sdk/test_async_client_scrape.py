"""`AsyncNotteClient.scrape`: `NotteClient.scrape` as a coroutine, sending the same requests.

Each scenario runs once through `NotteClient` and once through `AsyncNotteClient` behind the same
answers; both must send the same requests (session start, goto, scrape, stop) and return or raise
the same.
"""

import asyncio
import inspect
import json
import re
from typing import Any

import pytest
from notte_core.actions import GotoAction
from notte_core.errors import NotteBaseError
from notte_core.observation import SerializedError
from notte_sdk import AsyncNotteClient, NotteClient
from notte_sdk.errors import NotteAPIError

from tests.sdk.test_async_resources import Exchange, exchange_async, exchange_sync
from tests.sdk.test_async_sessions import CLOSED, SESSION, STOP, Product, executed, router, same_signature
from tests.sdk.test_generated_endpoints import SERVER

URL = "https://example.com"
START = ("POST", "/sessions/start")
GOTO = ("POST", "/sessions/s-1/page/execute")
SCRAPE = ("POST", "/sessions/s-1/page/scrape")
MARKDOWN = {"markdown": "# page"}
STRUCTURED = {"markdown": "", "structured": {"success": True, "data": {"name": "lamp"}}}
FAILED = {"markdown": "", "structured": {"success": False, "error": "nothing", "data": None}}

Routes = dict[tuple[str, str], list[tuple[int, Any]]]


def routes(scrape: tuple[int, Any], goto: dict[str, Any] | None = None) -> Routes:
    return {
        START: [(200, SESSION)],
        GOTO: [(200, goto or executed(GotoAction(url=URL)))],
        SCRAPE: [scrape],
        STOP: [(200, CLOSED)],
    }


def same_on_both(answers: Routes, monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> Exchange:
    """`client.scrape(URL, **kwargs)` on both clients; they must send and return the same."""
    expected = exchange_sync(monkeypatch, router(answers), lambda client: client.scrape(URL, **kwargs))
    actual = asyncio.run(exchange_async(monkeypatch, router(answers), lambda client: client.scrape(URL, **kwargs)))
    assert actual == expected
    return expected


def sent(exchange: Exchange) -> list[tuple[str, str]]:
    return [(call.method, call.url.removeprefix(SERVER)) for call in exchange.calls]


# ---------------------------------------------------------------------------
# Same signature and docstring


def test_async_scrape_has_the_sync_overloads() -> None:
    same_signature(NotteClient.scrape, AsyncNotteClient.scrape)


def test_async_scrape_has_the_sync_docstring() -> None:
    def prose(method: Any) -> str:
        return re.sub(r"```python\n.*?```", "```python```", inspect.getdoc(method) or "", flags=re.S)

    assert prose(AsyncNotteClient.scrape) == prose(NotteClient.scrape)
    examples = re.findall(r"```python\n(.*?)```", inspect.getdoc(AsyncNotteClient.scrape) or "", flags=re.S)
    assert len(examples) == 2
    for example in examples:
        assert "async with AsyncNotteClient() as client:" in example
        assert "await client.scrape(" in example
        assert "NotteClient()" not in example.replace("AsyncNotteClient()", "")


# ---------------------------------------------------------------------------
# Same requests


@pytest.mark.parametrize(
    "scrape,kwargs,outcome",
    [
        (MARKDOWN, {"only_main_content": False}, "# page"),
        (STRUCTURED, {"response_format": Product, "instructions": "the product"}, {"name": "lamp"}),
        (STRUCTURED, {"instructions": "the product"}, {"name": "lamp"}),
        (
            FAILED,
            {"response_format": Product, "raise_on_failure": False},
            {"success": False, "error": "nothing", "data": None},
        ),
        (FAILED, {"instructions": "the product", "raise_on_failure": False}, None),
    ],
    ids=["markdown", "response_format", "instructions", "response_format-no-raise", "instructions-no-raise"],
)
def test_scrape_sends_the_same_requests(
    monkeypatch: pytest.MonkeyPatch, scrape: dict[str, Any], kwargs: dict[str, Any], outcome: Any
) -> None:
    exchange = same_on_both(routes((200, scrape)), monkeypatch, **kwargs)
    assert sent(exchange) == [START, GOTO, SCRAPE, STOP]
    assert exchange.calls[-1].params == {"close_reason": "manual"}
    goto = json.loads(exchange.calls[1].data)
    assert goto["type"] == "goto" and goto["url"] == URL
    body = json.loads(exchange.calls[2].data)
    if "response_format" in kwargs:
        assert body["response_format"]["title"] == "Product"
    if outcome is not None:
        assert exchange.outcome == ("ok", outcome)
    else:
        # The structured wrapper without a response model: its fields are what the API sent.
        assert exchange.outcome[0] == "ok" and exchange.outcome[1]["success"] is False


def test_failed_structured_scrape_raises_the_same(monkeypatch: pytest.MonkeyPatch) -> None:
    exchange = same_on_both(routes((200, FAILED)), monkeypatch, response_format=Product)
    assert exchange.outcome[0] == "error"
    assert sent(exchange) == [START, GOTO, SCRAPE, STOP]
    assert exchange.calls[-1].params == {"close_reason": "error"}


# ---------------------------------------------------------------------------
# Failures stop the session


def test_failed_scrape_request_stops_the_session(monkeypatch: pytest.MonkeyPatch) -> None:
    exchange = same_on_both(routes((500, {"detail": "boom"})), monkeypatch, only_main_content=False)
    assert exchange.outcome[:2] == ("error", NotteAPIError)
    assert sent(exchange) == [START, GOTO, SCRAPE, STOP]
    assert exchange.calls[-1].params == {"close_reason": "error"}


def test_goto_that_threw_raises_and_stops_the_session(monkeypatch: pytest.MonkeyPatch) -> None:
    error = SerializedError(
        error_type="NotteBaseError", dev_message="no page", user_message="no page", agent_message="no page"
    )
    goto = {**executed(GotoAction(url=URL), success=False), "exception_detail": error.model_dump(mode="json")}
    exchange = same_on_both(routes((200, MARKDOWN), goto=goto), monkeypatch)
    assert exchange.outcome[0] == "error" and issubclass(exchange.outcome[1], NotteBaseError)
    assert sent(exchange) == [START, GOTO, STOP]
    assert exchange.calls[-1].params == {"close_reason": "error"}


def test_failed_goto_without_an_exception_still_scrapes(monkeypatch: pytest.MonkeyPatch) -> None:
    # Navigation is best effort: a goto that reports a failure but threw nothing scrapes what loaded.
    goto = executed(GotoAction(url=URL), success=False)
    exchange = same_on_both(routes((200, MARKDOWN), goto=goto), monkeypatch)
    assert exchange.outcome == ("ok", "# page")
    assert sent(exchange) == [START, GOTO, SCRAPE, STOP]
