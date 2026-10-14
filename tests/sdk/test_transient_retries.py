import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from notte_sdk._retry import backoff_delay, is_retryable_exception, parse_retry_after, retry_delay
from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from notte_sdk.endpoints.sessions import RemoteSession
from notte_sdk.errors import NotteAPIError
from notte_sdk.types import SessionStartRequest
from pydantic import BaseModel
from urllib3.exceptions import MaxRetryError, NewConnectionError


def response(status: int, retry_after: str | None = None) -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result._content_consumed = True
    result._content = json.dumps({"message": "unavailable", "status": status}).encode()
    if retry_after is not None:
        result.headers["Retry-After"] = retry_after
    return result


@pytest.fixture
def transport(monkeypatch):
    client = BaseClient(SimpleNamespace(max_retries=2), None, api_key="test-key")
    client._send = Mock()
    sleep = Mock()
    monkeypatch.setattr("notte_sdk.endpoints.base.time.sleep", sleep)
    return client, sleep


def send(client: BaseClient, method="GET", files=None):
    endpoint = NotteEndpoint(path="test", response=BaseModel, method=method)
    if files is not None:
        endpoint = endpoint.model_copy(update={"files": files})
    return client._send_with_retries(endpoint, url="https://api.example/test", headers={}, params=None, timeout=1)


@pytest.mark.parametrize(
    "method,status,retried",
    [
        ("GET", 502, True),
        ("GET", 504, True),
        ("POST", 502, False),
        ("POST", 504, False),
        ("POST", 503, True),
        ("POST", 529, True),
        ("GET", 500, False),
        ("GET", 429, False),
    ],
)
def test_status_retries(transport, method, status, retried):
    client, sleep = transport
    failed, success = response(status, "0"), response(200)
    client._send.side_effect = [failed, success]
    assert send(client, method) is (success if retried else failed)
    assert client._send.call_count == (2 if retried else 1)
    assert sleep.call_count == int(retried)


@pytest.mark.parametrize("status", [503, 529])
def test_retry_budget_and_disabled_retries(transport, status):
    client, sleep = transport
    failed = response(status, "0")
    client._send.return_value = failed
    assert send(client) is failed
    assert client._send.call_count == 3
    assert sleep.call_count == 2
    client.root_client.max_retries = 0
    client._send.reset_mock()
    sleep.reset_mock()
    assert send(client) is failed
    client._send.assert_called_once()
    sleep.assert_not_called()


def test_connection_exception_shapes(transport):
    client, sleep = transport
    refused = requests.ConnectionError(MaxRetryError(None, "/", NewConnectionError(None, "refused")))
    client._send.side_effect = [refused, response(200)]
    assert send(client, "POST").status_code == 200
    sleep.assert_called_once()
    assert is_retryable_exception(requests.ConnectTimeout(), "POST")
    assert is_retryable_exception(requests.ReadTimeout(), "GET")
    assert not is_retryable_exception(requests.ReadTimeout(), "POST")
    assert is_retryable_exception(requests.ConnectionError("reset"), "GET")
    assert not is_retryable_exception(requests.ConnectionError("reset"), "POST")
    assert not is_retryable_exception(requests.exceptions.SSLError(), "GET")


@pytest.mark.parametrize("header,delay", [("4", 4), ("20", 20), ("21", None)])
def test_retry_after_waits_and_cap(transport, header, delay):
    client, sleep = transport
    failed, success = response(503, header), response(200)
    client._send.side_effect = [failed, success]
    assert send(client) is (failed if delay is None else success)
    if delay is None:
        sleep.assert_not_called()
    else:
        sleep.assert_called_once_with(delay)


def test_retry_after_dates_and_backoff():
    assert parse_retry_after("Wed, 14 Oct 2026 12:00:04 GMT", now=1791979200) == 4
    assert parse_retry_after("invalid") is None
    assert parse_retry_after("-1") is None
    assert backoff_delay(0, rand=lambda: 0.5) == 0.5
    assert backoff_delay(20, rand=lambda: 1) == 10
    assert retry_delay(0, "invalid", rand=lambda: 0.5) == 0.5


@pytest.mark.parametrize("wrapped", [False, True])
def test_upload_replays_payload(transport, wrapped):
    client, _ = transport
    payload = BytesIO(b"upload content")
    bodies = []

    def attempt(endpoint, **kwargs):
        bodies.append(payload.read())
        return response(503 if len(bodies) == 1 else 200, "0")

    client._send.side_effect = attempt
    upload = ("test.txt", payload, "text/plain") if wrapped else payload
    assert send(client, "POST", files={"file": upload}).status_code == 200
    assert bodies == [b"upload content", b"upload content"]


def test_nonseekable_upload_is_not_retried(transport):
    client, sleep = transport
    failed = response(503, "0")
    client._send.return_value = failed
    assert send(client, "POST", files={"file": ("test.txt", iter([b"data"]))}) is failed
    client._send.assert_called_once()
    sleep.assert_not_called()


@pytest.mark.parametrize("status", [503, 529])
@pytest.mark.parametrize("max_retries", [0, 2])
def test_session_start_does_not_multiply_exhausted_retries(status, max_retries, monkeypatch):
    sleep = Mock()
    monkeypatch.setattr("notte_sdk.endpoints.sessions.time.sleep", sleep)
    session = object.__new__(RemoteSession)
    error = NotteAPIError(path="sessions/start", response=response(status))
    session.response = None
    session.request = SessionStartRequest()
    session.client = SimpleNamespace(max_retries=max_retries, start=Mock(side_effect=error))
    with pytest.raises(NotteAPIError) as caught:
        session.start()
    assert caught.value is error
    assert session.client.start.call_count == (1 if max_retries else 3)
    assert sleep.call_count == (2 if max_retries == 0 and status == 529 else 0)
