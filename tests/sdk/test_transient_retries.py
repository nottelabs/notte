import socket
import ssl
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

import httpcore
import httpx
import pytest
from notte_sdk._retry import backoff_delay, is_retryable_exception, parse_retry_after, retry_delay
from notte_sdk._transport import send_with_retries, translate_error
from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from notte_sdk.endpoints.sessions import RemoteSession
from notte_sdk.errors import (
    NotteAPIError,
    NotteConnectionError,
    NotteConnectTimeoutError,
    NotteReadTimeoutError,
    NotteRequestError,
    NotteSSLError,
)
from notte_sdk.types import SessionStartRequest
from pydantic import BaseModel


def response(status: int, retry_after: str | None = None) -> httpx.Response:
    headers = {} if retry_after is None else {"Retry-After": retry_after}
    return httpx.Response(status, json={"message": "unavailable", "status": status}, headers=headers)


def failure(error: httpx.HTTPError, cause: BaseException | None = None, *, body: bool = False) -> NotteRequestError:
    """The SDK exception for an httpx failure, chained as the transport raises it.

    httpx raises from the httpcore error, which httpcore re-raised `from None`:
    its socket or TLS error is only its `__context__`.
    """
    if cause is not None:
        inner = httpcore.ConnectError(str(cause))
        inner.__context__ = cause
        inner.__suppress_context__ = True
        error.__cause__ = inner
    try:
        raise translate_error(error, body=body) from error
    except NotteRequestError as translated:
        return translated


@pytest.fixture
def transport(monkeypatch):
    client = BaseClient(SimpleNamespace(max_retries=2), None, api_key="test-key")
    client._send = Mock()
    sleep = Mock()
    monkeypatch.setattr("notte_sdk._transport.time.sleep", sleep)
    return client, sleep


def send(client: BaseClient, method="GET", files=None):
    endpoint = NotteEndpoint(path="test", response=BaseModel, method=method)
    if files is not None:
        endpoint = endpoint.model_copy(update={"files": files})
    return send_with_retries(
        endpoint,
        lambda remaining: client._send(endpoint, timeout=remaining),
        max_retries=client.max_retries,
        timeout=60,
    )


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
    refused = failure(httpx.ConnectError("refused"), ConnectionRefusedError(61, "refused"))
    client._send.side_effect = [refused, response(200)]
    assert send(client, "POST").status_code == 200
    sleep.assert_called_once()
    assert is_retryable_exception(NotteConnectTimeoutError(), "POST")
    assert is_retryable_exception(NotteReadTimeoutError(), "GET")
    assert not is_retryable_exception(NotteReadTimeoutError(), "POST")
    assert is_retryable_exception(NotteConnectionError("reset"), "GET")
    assert not is_retryable_exception(NotteConnectionError("reset"), "POST")
    assert not is_retryable_exception(NotteSSLError(), "GET")


IDEMPOTENT_ONLY = {"GET": True, "POST": False}
EVERY_METHOD = {"GET": True, "POST": True}
NEVER = {"GET": False, "POST": False}


@pytest.mark.parametrize(
    "error,cause,body,retried",
    [
        # The connection never opened: nothing was sent.
        (httpx.ConnectError("refused"), ConnectionRefusedError(61, "refused"), False, EVERY_METHOD),
        (httpx.ConnectError("unreachable"), OSError(51, "unreachable"), False, EVERY_METHOD),
        (httpx.ConnectTimeout("connect"), None, False, EVERY_METHOD),
        (httpx.PoolTimeout("pool"), None, False, EVERY_METHOD),
        # requests treated an unknown host and an exhausted handshake reset as possibly sent.
        (httpx.ConnectError("dns"), socket.gaierror(8, "nodename"), False, IDEMPOTENT_ONLY),
        (httpx.ConnectError("reset"), ConnectionResetError(54, "reset"), False, IDEMPOTENT_ONLY),
        (httpx.ReadTimeout("read"), None, False, IDEMPOTENT_ONLY),
        (httpx.WriteTimeout("write"), None, False, IDEMPOTENT_ONLY),
        (httpx.ReadError("reset"), ConnectionResetError(54, "reset"), False, IDEMPOTENT_ONLY),
        (httpx.WriteError("pipe"), BrokenPipeError(32, "pipe"), False, IDEMPOTENT_ONLY),
        (httpx.RemoteProtocolError("Server disconnected"), None, False, IDEMPOTENT_ONLY),
        (httpx.ProxyError("proxy"), None, False, IDEMPOTENT_ONLY),
        # A body read that times out, like requests' ConnectionError from iter_content.
        (httpx.ReadTimeout("read"), None, True, IDEMPOTENT_ONLY),
        # A body broken mid-read, like requests' ChunkedEncodingError.
        (httpx.RemoteProtocolError("incomplete"), None, True, NEVER),
        (httpx.ReadError("reset"), ConnectionResetError(54, "reset"), True, NEVER),
        # TLS failures, in the handshake or later.
        (httpx.ConnectError("cert"), ssl.SSLCertVerificationError("bad cert"), False, NEVER),
        (httpx.ConnectError("eof"), ssl.SSLEOFError("eof"), False, NEVER),
        (httpx.ReadError("tls"), ssl.SSLError("bad record mac"), True, NEVER),
        (httpx.TooManyRedirects("redirects"), None, False, NEVER),
        (httpx.UnsupportedProtocol("ftp"), None, False, NEVER),
        (httpx.DecodingError("gzip"), None, True, NEVER),
    ],
)
def test_retry_classification_matches_requests(error, cause, body, retried):
    translated = failure(error, cause, body=body)
    assert {method: is_retryable_exception(translated, method) for method in ("GET", "POST")} == retried


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
@pytest.mark.parametrize("offset", [0, 7])
def test_upload_replays_payload(transport, wrapped, offset):
    client, _ = transport
    payload = BytesIO(b"upload content")
    payload.seek(offset)
    bodies = []

    def attempt(endpoint, **kwargs):
        bodies.append(payload.read())
        return response(503 if len(bodies) == 1 else 200, "0")

    client._send.side_effect = attempt
    upload = ("test.txt", payload, "text/plain") if wrapped else payload
    assert send(client, "POST", files={"file": upload}).status_code == 200
    assert bodies == [b"upload content"[offset:]] * 2


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


def test_retry_after_cannot_exceed_request_deadline(transport):
    client, sleep = transport
    failed = response(503, "2")
    client._send.return_value = failed
    endpoint = NotteEndpoint(path="poll", response=BaseModel, method="POST")
    assert (
        send_with_retries(endpoint, lambda remaining: client._send(timeout=remaining), max_retries=3, timeout=1)
        is failed
    )
    client._send.assert_called_once()
    sleep.assert_not_called()


def test_retries_use_remaining_time(transport, monkeypatch):
    client, sleep = transport
    now = [0.0]
    monkeypatch.setattr("notte_sdk._transport.time.monotonic", lambda: now[0])
    sleep.side_effect = lambda seconds: now.__setitem__(0, now[0] + seconds)
    client._send.side_effect = [response(503, "2"), response(200)]
    endpoint = NotteEndpoint(path="poll", response=BaseModel, method="POST")
    assert (
        send_with_retries(
            endpoint, lambda remaining: client._send(timeout=remaining), max_retries=3, timeout=10
        ).status_code
        == 200
    )
    assert [call.kwargs["timeout"] for call in client._send.call_args_list] == [10, 8]
