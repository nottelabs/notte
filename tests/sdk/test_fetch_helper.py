"""Remote `fetch()`: the request runs in the page via `evaluate_js` and comes back requests-shaped."""

import datetime as dt
import json

import pytest
from notte_core.actions import EvaluateJsAction
from notte_core.browser.observation import ExecutionResult
from notte_core.data.fetch import FetchResponse, build_fetch_script
from notte_core.data.space import DataSpace
from notte_core.errors.actions import FetchResponseDecodeError, FetchStatusError

from tests.sdk.test_execute_raise_on_failure import over_the_wire, remote_session


def envelope(status: int = 200, text: str = '{"ok": true}', url: str = "https://example.com/api") -> str:
    return json.dumps({"status": status, "url": url, "headers": {"content-type": "application/json"}, "text": text})


def eval_result(markdown: str) -> ExecutionResult:
    now = dt.datetime.now(dt.timezone.utc)
    return ExecutionResult(
        action=EvaluateJsAction(code="fetch"),
        success=True,
        message="ok",
        data=DataSpace(markdown=markdown),
        started_at=now,
        ended_at=now,
    )


# --- the script -----------------------------------------------------------------


def test_script_defaults_to_a_credentialed_get_with_no_body() -> None:
    script = build_fetch_script("/api")

    assert script.startswith("(async () => {")
    assert '"method": "GET"' in script
    assert '"credentials": "include"' in script
    assert 'fetch("/api", init)' in script
    assert '"body"' not in script
    assert "AbortController" not in script


def test_script_appends_params_to_the_query_string() -> None:
    assert 'fetch("/api?page=2&q=a+b", init)' in build_fetch_script("/api", params={"page": 2, "q": "a b"})
    assert 'fetch("/api?x=1&page=2", init)' in build_fetch_script("/api?x=1", params={"page": 2})


def test_script_serialises_a_json_body_and_sets_the_content_type() -> None:
    script = build_fetch_script("/graphql", method="post", json_body={"query": "{ me }"})

    assert '"method": "POST"' in script
    assert '"Content-Type": "application/json"' in script
    assert json.dumps(json.dumps({"query": "{ me }"})) in script


def test_script_keeps_a_caller_content_type() -> None:
    script = build_fetch_script("/x", json_body={}, headers={"content-type": "application/graphql-response+json"})

    assert script.count("ontent-") == 1
    assert "application/graphql-response+json" in script


def test_script_form_encodes_a_mapping_and_passes_a_string_through() -> None:
    form = build_fetch_script("/login", method="POST", data={"user": "a b", "pw": "c"})
    assert '"body": "user=a+b&pw=c"' in form
    assert '"Content-Type": "application/x-www-form-urlencoded"' in form

    raw = build_fetch_script("/raw", method="PUT", data="<xml/>")
    assert '"body": "<xml/>"' in raw
    assert "Content-Type" not in raw


def test_script_rejects_json_and_data_together() -> None:
    with pytest.raises(ValueError, match="either json or data"):
        _ = build_fetch_script("/x", json_body={}, data="y")


def test_script_aborts_after_the_timeout() -> None:
    script = build_fetch_script("/slow", timeout=2.5)

    assert "controller.abort(), 2500" in script
    assert "init.signal = controller.signal" in script
    with pytest.raises(ValueError, match="positive"):
        _ = build_fetch_script("/slow", timeout=0)


# --- the response ----------------------------------------------------------------


def test_fetch_returns_a_requests_shaped_response() -> None:
    session = remote_session(over_the_wire(eval_result(envelope())))

    response = session.fetch("/api")

    assert isinstance(response, FetchResponse)
    assert response.status_code == 200
    assert response.ok
    assert response.json() == {"ok": True}
    assert response.headers["content-type"] == "application/json"
    assert response.url == "https://example.com/api"
    response.raise_for_status()


def test_fetch_returns_http_errors_and_raises_only_when_asked() -> None:
    session = remote_session(over_the_wire(eval_result(envelope(status=403, text="denied"))))

    response = session.fetch("/api")

    assert response.status_code == 403
    assert not response.ok
    assert response.text == "denied"
    with pytest.raises(FetchStatusError, match="HTTP 403") as raised:
        response.raise_for_status()
    assert raised.value.status_code == 403


def test_fetch_rejects_an_unreadable_envelope() -> None:
    session = remote_session(over_the_wire(eval_result("not json")))

    with pytest.raises(FetchResponseDecodeError, match="unreadable"):
        _ = session.fetch("/api")
