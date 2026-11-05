"""`act()`, `choose()` and `check()` on cloud sessions: the requests sent, the results and the failures raised."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from notte_core.act import ActResult, Choice, NoActionFoundError
from notte_core.actions import ClickAction
from notte_core.errors import NotteBaseError
from notte_core.observation import utc_now
from notte_sdk.client import NotteClient
from notte_sdk.endpoints.page import ACT_TIMEOUT_SECONDS
from notte_sdk.endpoints.sessions import RemoteSession

from scripts.generate_sdk_endpoints import REQUEST_TIMEOUTS

from tests.sdk.test_async_resources import exchange_async, exchange_sync
from tests.sdk.test_generated_endpoints import SERVER, fake

SESSION_ID = "s-1"
NOW = utc_now().isoformat()


def act_result(status: str = "executed", *, success: bool = True, message: str | None = None) -> dict[str, Any]:
    execution = {
        "action": ClickAction(id="B1").model_dump(mode="json"),
        "success": success,
        "message": "ok" if success else "the element is gone",
        "started_at": NOW,
        "ended_at": NOW,
    }
    return {
        "instruction": "accept the cookies",
        "status": status,
        "action": ClickAction(id="B1").model_dump(mode="json") if status != "blocked" else None,
        "execution": execution if status == "executed" else None,
        "operation": "CLICK",
        "target": "B1",
        "confidence": 0.9,
        "message": message,
    }


CHOICE = {"choice": "pro", "probabilities": {"free": 0.1, "pro": 0.9}, "confidence": 0.8, "model": "jev"}


def _answers(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/page/act"):
        return httpx.Response(200, json=act_result())
    if path.endswith("/page/choose"):
        return httpx.Response(200, json=CHOICE)
    return httpx.Response(200, json={"probability": 0.75})


def _session(client: NotteClient, **options: Any) -> RemoteSession:
    with patch.object(type(client.sessions), "status", return_value=MagicMock(session_id=SESSION_ID)):
        return RemoteSession(SESSION_ID, _client=client.sessions, **options)


@pytest.fixture
def client() -> NotteClient:
    return NotteClient(api_key="test-api-key", server_url=SERVER)  # pragma: allowlist secret


@pytest.mark.asyncio
async def test_sync_and_async_clients_send_the_same_requests_and_parse_the_same_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def calls(notte: Any) -> Any:
        page = notte.sessions.page
        return (
            page.act(SESSION_ID, "type {{email}}", variables={"email": "jane@example.com"}, dry_run=True),
            page.choose(SESSION_ID, "Which plan?", {"free": "the free plan", "pro": "the pro plan"}),
            page.check(SESSION_ID, "Is it done?"),
        )

    async def acalls(notte: Any) -> Any:
        page = notte.sessions.page
        return (
            await page.act(SESSION_ID, "type {{email}}", variables={"email": "jane@example.com"}, dry_run=True),
            await page.choose(SESSION_ID, "Which plan?", {"free": "the free plan", "pro": "the pro plan"}),
            await page.check(SESSION_ID, "Is it done?"),
        )

    expected = exchange_sync(monkeypatch, _answers, calls)
    actual = await exchange_async(monkeypatch, _answers, acalls)
    assert actual == expected
    assert expected.outcome[0] == "ok"
    assert [(call.method, call.url) for call in expected.calls] == [
        ("POST", f"{SERVER}/sessions/{SESSION_ID}/page/act"),
        ("POST", f"{SERVER}/sessions/{SESSION_ID}/page/choose"),
        ("POST", f"{SERVER}/sessions/{SESSION_ID}/page/check"),
    ]
    assert [json.loads(call.data) for call in expected.calls] == [
        {
            "instruction": "type {{email}}",
            "variables": {"email": "jane@example.com"},
            "dry_run": True,
            "min_confidence": 0.0,
        },
        {"question": "Which plan?", "options": {"free": "the free plan", "pro": "the pro plan"}},
        {"question": "Is it done?"},
    ]
    # A step takes a few model calls: more than the default request timeout.
    assert all(call.timeout.get("read") == ACT_TIMEOUT_SECONDS for call in expected.calls)


def test_cloud_results_are_the_same_classes_as_a_local_sessions(client: NotteClient, monkeypatch) -> None:
    session = _session(client)
    _ = fake(monkeypatch, act_result())
    result = session.act("accept the cookies")
    assert type(result) is ActResult and result.status == "executed" and result.success
    assert result.action == ClickAction(id="B1")

    _ = fake(monkeypatch, CHOICE)
    choice = session.choose("Which plan?", ["free", "pro"])
    assert type(choice) is Choice and choice.choice == "pro"

    _ = fake(monkeypatch, {"probability": 0.75})
    assert session.check("Is it done?") == 0.75


def test_a_blocked_step_raises_as_on_a_local_session_unless_failures_are_returned(
    client: NotteClient, monkeypatch
) -> None:
    _ = fake(monkeypatch, act_result("blocked", message="file upload is not supported"))

    with pytest.raises(NoActionFoundError) as raised:
        _ = _session(client).act("upload my resume")
    assert raised.value.result is not None and raised.value.result.status == "blocked"
    assert "file upload is not supported" in raised.value.dev_message

    assert _session(client).act("upload my resume", raise_on_failure=False).status == "blocked"
    # The session's own default applies when the call does not say.
    assert _session(client, raise_on_failure=False).act("upload my resume").status == "blocked"


def test_an_action_that_failed_raises_its_error(client: NotteClient, monkeypatch) -> None:
    _ = fake(monkeypatch, act_result(success=False))

    with pytest.raises(NotteBaseError, match="the element is gone"):
        _ = _session(client).act("accept the cookies")
    result = _session(client).act("accept the cookies", raise_on_failure=False)
    assert result.status == "executed" and not result.success


@pytest.mark.parametrize("status", ["done", "proposed", "stale"])
def test_steps_that_ran_nothing_never_raise(client: NotteClient, monkeypatch, status: str) -> None:
    _ = fake(monkeypatch, act_result(status))
    assert _session(client).act("accept the cookies").status == status


def test_the_generated_low_level_bindings_wait_as_long_as_the_session_methods(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert {REQUEST_TIMEOUTS[name] for name in ("page_act", "page_choose", "page_check")} == {ACT_TIMEOUT_SECONDS}
    api = fake(monkeypatch, {"probability": 0.5})
    _ = client.sessions.check(SESSION_ID, question="Is it done?")
    assert api.calls[0].timeout.get("read") == ACT_TIMEOUT_SECONDS
