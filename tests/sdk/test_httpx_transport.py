"""The httpx transport behaves like the requests transport it replaced.

Where both libraries are involved, `requests` is the reference implementation.
"""

import datetime as dt
import gc
import json
import socket
import ssl
import threading
from collections.abc import Iterator
from email.message import Message
from email.parser import BytesParser
from enum import Enum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

import httpx
import pytest
import requests
from notte_sdk import NotteClient
from notte_sdk._retry import is_retryable_exception
from notte_sdk._transport import (
    _ssl_context,
    form_fields,
    get_text,
    http_client,
    iter_lines,
    multipart_files,
    send,
    stream,
    translate_error,
    with_query,
)
from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from notte_sdk.errors import (
    NotteAPIError,
    NotteConnectionError,
    NotteConnectTimeoutError,
    NotteHTTPStatusError,
    NotteInvalidURLError,
    NotteJSONDecodeError,
    NotteProxyError,
    NotteReadTimeoutError,
    NotteRequestTimeoutError,
    NotteSSLError,
    NotteStreamError,
    NotteTooManyRedirectsError,
)
from pydantic import BaseModel

from tests.sdk.test_handshake_transport import PROXY_VARIABLES, certificate  # noqa: F401

SERVER = "https://api.example.test"


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(BaseClient, "check_and_warn_version_mismatch", lambda _: None)
    monkeypatch.setattr("notte_sdk._transport.time.sleep", Mock())
    for name in (*PROXY_VARIABLES, "NO_PROXY", "no_proxy", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        monkeypatch.delenv(name, raising=False)


def serve(monkeypatch: pytest.MonkeyPatch, handler: Any) -> list[httpx.Request]:
    """Answer SDK requests with `handler` behind the real `http_client()` configuration."""
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client = http_client()
    client._transport = httpx.MockTransport(handle)
    monkeypatch.setattr("notte_sdk._transport.SharedHttpClient.get", lambda _: client)
    return seen


def api(max_retries: int = 0) -> BaseClient:
    key = "test-key"  # pragma: allowlist secret
    return BaseClient(SimpleNamespace(max_retries=max_retries), None, server_url=SERVER, api_key=key)


def endpoint(method: str = "GET", path: str = "resource") -> NotteEndpoint[BaseModel]:
    return NotteEndpoint(path=path, response=BaseModel, method=method)  # pyright: ignore[reportArgumentType]


class Raising(httpx.SyncByteStream):
    """A body that fails after its first chunk."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def __iter__(self) -> Iterator[bytes]:
        yield b'{"partial":'
        raise self.error


# ---------------------------------------------------------------------------
# Redirects


def test_redirects_are_followed_and_capped_at_requests_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    hops = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        step = int(request.url.params.get("step", "0"))
        if step < hops["count"]:
            return httpx.Response(302, headers={"location": f"{SERVER}/resource?step={step + 1}"})
        return httpx.Response(200, json={"step": step})

    seen = serve(monkeypatch, handler)
    hops["count"] = 30
    assert api()._request(endpoint()) == {"step": 30}
    assert len(seen) == 31
    hops["count"] = 31
    with pytest.raises(requests.TooManyRedirects) as error:
        _ = api()._request(endpoint())
    assert isinstance(error.value, NotteTooManyRedirectsError)


@pytest.mark.parametrize(
    "status,method,body", [(301, "GET", None), (302, "GET", None), (303, "GET", None), (307, "POST", '{"a":1}')]
)
def test_redirect_methods_match_requests(monkeypatch: pytest.MonkeyPatch, status: int, method: str, body: Any) -> None:
    class Body(BaseModel):
        a: int

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/resource":
            return httpx.Response(status, headers={"location": "/moved"})
        return httpx.Response(200, json={})

    seen = serve(monkeypatch, handler)
    _ = api()._request(endpoint("POST").with_request(Body(a=1)))
    assert [(r.method, r.url.path) for r in seen] == [("POST", "/resource"), (method, "/moved")]
    assert (seen[1].content.decode() or None) == body


@pytest.mark.parametrize("target,keeps_auth", [(f"{SERVER}/moved", True), ("https://other.example.test/moved", False)])
def test_cross_origin_redirect_drops_authorization(
    monkeypatch: pytest.MonkeyPatch, target: str, keeps_auth: bool
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/resource":
            return httpx.Response(302, headers={"location": target})
        return httpx.Response(200, json={})

    seen = serve(monkeypatch, handler)
    _ = api()._request(endpoint())
    assert ("authorization" in seen[1].headers) is keeps_auth
    # requests strips the same header in the same case.
    assert requests.Session().should_strip_auth(f"{SERVER}/resource", target) is not keeps_auth


# ---------------------------------------------------------------------------
# Exceptions


@pytest.mark.parametrize(
    "error,body,expected,compat",
    [
        (httpx.ConnectError("refused"), False, NotteConnectionError, requests.ConnectionError),
        (httpx.ConnectTimeout("connect"), False, NotteConnectTimeoutError, requests.ConnectTimeout),
        (httpx.ReadTimeout("read"), False, NotteReadTimeoutError, requests.ReadTimeout),
        (httpx.ReadTimeout("read"), True, NotteReadTimeoutError, requests.Timeout),
        (httpx.WriteTimeout("write"), False, NotteRequestTimeoutError, requests.Timeout),
        (httpx.ReadError("reset"), False, NotteConnectionError, requests.ConnectionError),
        (httpx.RemoteProtocolError("disconnected"), False, NotteConnectionError, requests.ConnectionError),
        (httpx.RemoteProtocolError("incomplete"), True, NotteStreamError, requests.exceptions.ChunkedEncodingError),
        (httpx.ProxyError("proxy"), False, NotteProxyError, requests.exceptions.ProxyError),
        (httpx.TooManyRedirects("redirects"), False, NotteTooManyRedirectsError, requests.TooManyRedirects),
        (httpx.UnsupportedProtocol("ftp"), False, NotteInvalidURLError, requests.exceptions.InvalidURL),
        (httpx.InvalidURL("bad"), False, NotteInvalidURLError, requests.exceptions.InvalidURL),
    ],
)
def test_httpx_errors_translate_to_sdk_and_requests_classes(
    error: Exception, body: bool, expected: type[Exception], compat: type[Exception]
) -> None:
    translated = translate_error(error, body=body)
    assert type(translated) is expected
    assert isinstance(translated, compat)
    assert isinstance(translated, requests.RequestException)
    # Transport failures are OSErrors, as before. Only an invalid URL is also a ValueError, as in requests.
    assert isinstance(translated, OSError)
    assert isinstance(translated, ValueError) is issubclass(compat, ValueError)


def test_transport_errors_reach_callers_as_sdk_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("[Errno 61] Connection refused")

    _ = serve(monkeypatch, handler)
    with pytest.raises(requests.ConnectionError) as error:
        _ = api()._request(endpoint())
    assert isinstance(error.value, NotteConnectionError)
    assert isinstance(error.value.__cause__, httpx.ConnectError)


def test_real_connection_refused_is_retried_for_every_method(monkeypatch: pytest.MonkeyPatch) -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.close()
    sleep = Mock()
    monkeypatch.setattr("notte_sdk._transport.time.sleep", sleep)
    client = BaseClient(SimpleNamespace(max_retries=2), None, server_url=f"http://127.0.0.1:{port}", api_key="k")
    with pytest.raises(NotteConnectionError) as error:
        _ = client._request(endpoint("POST"), timeout=5)
    assert is_retryable_exception(error.value, "POST")
    assert sleep.call_count == 2


def test_root_cause_ignores_an_error_the_caller_was_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadError("reset")

    _ = serve(monkeypatch, handler)
    try:
        raise ssl.SSLError("unrelated")
    except ssl.SSLError:
        with pytest.raises(NotteConnectionError) as error:
            _ = api()._request(endpoint())
    assert not isinstance(error.value, NotteSSLError)


@pytest.mark.parametrize("method,retried", [("GET", False), ("POST", False)])
def test_broken_body_is_a_stream_error_and_not_retried(
    monkeypatch: pytest.MonkeyPatch, method: str, retried: bool
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=Raising(httpx.RemoteProtocolError("peer closed connection")))

    seen = serve(monkeypatch, handler)
    with pytest.raises(requests.exceptions.ChunkedEncodingError) as error:
        _ = api(max_retries=3)._request(endpoint(method))
    assert isinstance(error.value, NotteStreamError)
    assert len(seen) == 1


@pytest.mark.parametrize("method,attempts", [("GET", 2), ("POST", 1)])
def test_body_read_timeout_is_retried_for_idempotent_methods(
    monkeypatch: pytest.MonkeyPatch, method: str, attempts: int
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if len(seen) == 1:
            return httpx.Response(200, stream=Raising(httpx.ReadTimeout("timed out")))
        return httpx.Response(200, json={"ok": True})

    seen = serve(monkeypatch, handler)
    if attempts == 1:
        with pytest.raises(NotteReadTimeoutError):
            _ = api(max_retries=3)._request(endpoint(method))
    else:
        assert api(max_retries=3)._request(endpoint(method)) == {"ok": True}
    assert len(seen) == attempts


def test_retry_deadline_is_a_requests_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [0.0]
    monkeypatch.setattr("notte_sdk._transport.time.monotonic", lambda: now[0])
    # The backoff sleep overshoots the request's time budget.
    monkeypatch.setattr("notte_sdk._transport.time.sleep", lambda _: now.__setitem__(0, now[0] + 10))

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    _ = serve(monkeypatch, handler)
    with pytest.raises(requests.Timeout, match="retry deadline exceeded") as error:
        _ = api(max_retries=5)._request(endpoint("POST"), timeout=4)
    assert isinstance(error.value, NotteRequestTimeoutError)


def test_invalid_json_success_is_a_json_decode_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _ = serve(monkeypatch, lambda request: httpx.Response(200, content=b"<html>"))
    with pytest.raises(json.JSONDecodeError) as error:
        _ = api()._request(endpoint())
    assert isinstance(error.value, NotteJSONDecodeError)
    assert isinstance(error.value, requests.JSONDecodeError)
    assert error.value.doc == "<html>"


def test_api_errors_accept_httpx_and_requests_responses() -> None:
    httpx_response = httpx.Response(404, json={"detail": "missing"})
    requests_response = requests.Response()
    requests_response.status_code = 404
    requests_response._content = b'{"detail": "missing"}'
    for response in (httpx_response, requests_response):
        error = NotteAPIError(path="resource", response=response)
        assert (error.status_code, error.error) == (404, {"detail": "missing"})
    text = NotteAPIError(path="resource", response=httpx.Response(502, text="Bad gateway"))
    assert text.error == {"message": "Bad gateway"}


def test_raise_for_status_error_keeps_the_response(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = serve(monkeypatch, lambda request: httpx.Response(404, text="gone"))
    with pytest.raises(requests.HTTPError, match="404 Client Error: Not Found for url: https://files.test/a") as error:
        _ = api().request_download("https://files.test/a", str(tmp_path / "a"))
    assert isinstance(error.value, NotteHTTPStatusError)
    response = error.value.response
    assert response is not None
    assert (response.status_code, response.text, response.headers["content-length"]) == (404, "gone", "4")


class Body(BaseModel):
    value: str


@pytest.mark.parametrize("stream_lines", [False, True])
def test_function_run_requests_are_sent_once(monkeypatch: pytest.MonkeyPatch, stream_lines: bool) -> None:
    seen = serve(monkeypatch, lambda request: httpx.Response(503, json={"detail": "busy"}))
    run = endpoint("POST").with_request(Body(value="x"))
    with pytest.raises(NotteAPIError) as error:
        if stream_lines:
            with api(max_retries=3)._stream_lines(run, headers={"x-run": "1"}, timeout=5):
                pass
        else:
            _ = api(max_retries=3)._request_once(run, headers={"x-run": "1"}, timeout=5)
    # Never retried, even for a status that is retried elsewhere; the error body is read.
    assert error.value.status_code == 503
    assert error.value.error == {"detail": "busy"}
    assert len(seen) == 1
    assert seen[0].method == "POST"
    assert (seen[0].headers["x-run"], seen[0].headers["content-type"]) == ("1", "application/json")
    assert seen[0].content == b'{"value":"x"}'


def test_streamed_lines_are_split_as_they_arrive(monkeypatch: pytest.MonkeyPatch) -> None:
    class Events(httpx.SyncByteStream):
        def __iter__(self) -> Iterator[bytes]:
            yield b'data: {"type": "log"}\n\nda'
            yield b'ta: {"type": "result"}\n'

    _ = serve(monkeypatch, lambda request: httpx.Response(200, stream=Events()))
    with api()._stream_lines(endpoint("POST"), headers={}, timeout=5) as lines:
        assert list(lines) == ['data: {"type": "log"}', 'data: {"type": "result"}']


def test_public_downloads_carry_no_api_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[httpx.Request] = []
    real = http_client

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/code.py":
            return httpx.Response(302, headers={"location": "/moved.py"})
        if request.url.path == "/moved.py":
            return httpx.Response(200, text="def run(): ...")
        return httpx.Response(404, text="gone")

    def client() -> httpx.Client:
        created = real()
        created._transport = httpx.MockTransport(handle)
        return created

    monkeypatch.setattr("notte_sdk._transport.http_client", client)
    # Redirects are followed, as requests.get followed them.
    assert get_text("https://files.test/code.py", timeout=5) == "def run(): ..."
    assert "authorization" not in seen[0].headers
    with pytest.raises(requests.HTTPError) as error:
        _ = get_text("https://files.test/missing.py", timeout=5)
    assert isinstance(error.value, NotteHTTPStatusError)


# ---------------------------------------------------------------------------
# Encoding


class Color(str, Enum):
    RED = "red"


@pytest.mark.parametrize(
    "params",
    [
        {"flag": True, "off": False, "count": 0, "ratio": 0.5},
        {"ids": ["a", "b"], "skip": None, "empty": ""},
        {"text": "a b&c=d/é?#", "plus": "1+1"},
        {"color": Color.RED},
        {"at": dt.datetime(2026, 10, 22, 12, tzinfo=dt.timezone.utc), "window": dt.timedelta(minutes=5)},
        {},
    ],
)
def test_query_strings_match_requests(params: dict[str, Any]) -> None:
    url = f"{SERVER}/sessions/a%2Fb"
    expected = requests.Request("GET", url, params=params).prepare().url
    assert with_query(url, params) == expected
    # httpx sends the query unchanged.
    assert str(httpx.Request("GET", with_query(url, params)).url) == expected


def multipart(content_type: str, body: bytes) -> list[tuple[str, str | None, bytes, str | None]]:
    message = BytesParser().parsebytes(f"Content-Type: {content_type}\r\n\r\n".encode() + body)
    parts = []
    for part in message.get_payload():
        assert isinstance(part, Message)
        content = part.get_payload(decode=True)
        assert isinstance(content, bytes)
        name = part.get_param("name", header="content-disposition")
        assert isinstance(name, str)
        parts.append((name, part.get_filename(), content, part.get("content-type")))
    return parts


@pytest.mark.parametrize("named", [True, False])
def test_multipart_fields_and_files_match_requests(tmp_path: Any, named: bool) -> None:
    data = {"name": "fixture", "restricted": False, "count": 3, "tags": ["a", "b"], "skipped": None}
    path = tmp_path / "function.py"
    path.write_bytes(b"def run(): return 1\n")

    def upload() -> Any:
        return path.open("rb") if named else BytesIO(b"def run(): return 1\n")

    with upload() as handle:
        prepared = requests.Request("POST", SERVER, data=data, files={"file": handle}).prepare()
    with upload() as handle:
        request = httpx.Request("POST", SERVER, data=form_fields(data), files=multipart_files({"file": handle}))
        _ = request.read()
    assert prepared.body is not None and isinstance(prepared.body, bytes)
    expected = multipart(prepared.headers["Content-Type"], prepared.body)
    actual = multipart(request.headers["content-type"], request.content)
    # Same fields, values, filenames and bytes, in the same order.
    assert [part[:3] for part in actual] == [part[:3] for part in expected]
    assert expected[-1][1] == ("function.py" if named else "file")
    # The one difference: httpx always labels a file part with a content type.
    assert expected[-1][3] is None
    assert actual[-1][3] == ("text/x-python" if named else "application/octet-stream")


@pytest.mark.parametrize(
    "chunks",
    [
        [b"data: one\n\ndata: two\n\n"],
        [b"data: o", b"ne\r", b"\ndata: two"],
        [b"data: one\r\n", b"\r\n", b"data: \xe2\x80\xa8 two\n"],
        [b"no newline at end"],
        [b"a\rb\n", b"", b"c"],
    ],
)
def test_iter_lines_matches_requests(chunks: list[bytes]) -> None:
    reference = requests.Response()
    reference.iter_content = lambda chunk_size=1, decode_unicode=False: iter(chunks)  # pyright: ignore[reportAttributeAccessIssue]
    response = httpx.Response(200, stream=httpx.ByteStream(b""))
    response.iter_bytes = lambda chunk_size=None: iter(chunks)  # pyright: ignore[reportAttributeAccessIssue]
    assert list(iter_lines(response)) == list(reference.iter_lines())


# ---------------------------------------------------------------------------
# Configuration


def test_requests_ca_bundle_variables_are_honored(certificate: Any, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    _, cert_path = certificate

    def loaded() -> int:
        return _ssl_context().cert_store_stats()["x509"]

    default = loaded()
    assert default > 1
    for name in ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        monkeypatch.setenv(name, cert_path)
        assert loaded() == 1
        monkeypatch.delenv(name)
    # requests ignores SSL_CERT_FILE, so the SDK does too.
    monkeypatch.setenv("SSL_CERT_FILE", cert_path)
    assert loaded() == default


def test_environment_proxies_are_honored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.test:3128")
    monkeypatch.setenv("NO_PROXY", "direct.test")
    with http_client() as client:
        proxied = client._transport_for_url(httpx.URL("https://api.notte.cc/health"))
        direct = client._transport_for_url(httpx.URL("https://direct.test/health"))
        assert proxied is not client._transport
        assert direct is client._transport
    assert requests.utils.get_environ_proxies("https://api.notte.cc") == {
        "https": "http://proxy.test:3128",
        "no": "direct.test",
    }
    assert requests.utils.get_environ_proxies("https://direct.test") == {}


def test_request_timeouts_and_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = serve(monkeypatch, lambda request: httpx.Response(200, json={}))
    client = api()
    _ = client._request(endpoint(), timeout=12)
    client.health_check()
    assert seen[0].extensions["timeout"] == {"connect": 12, "read": 12, "write": 12, "pool": 12}
    # Like requests, a call without a timeout has none.
    assert seen[1].extensions["timeout"] == {"connect": None, "read": None, "write": None, "pool": None}
    headers = seen[0].headers
    assert headers["authorization"] == "Bearer test-key"
    assert headers["x-notte-request-origin"] == "sdk-python"
    assert headers["accept"] == "*/*"
    assert headers["connection"] == "keep-alive"
    assert "gzip" in headers["accept-encoding"]
    # The default user agent names the HTTP library, as python-requests/X did.
    assert headers["user-agent"] == f"python-httpx/{httpx.__version__}"


def test_cookies_are_not_kept_between_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = serve(monkeypatch, lambda request: httpx.Response(200, json={}, headers={"set-cookie": "__cf_bm=x; Path=/"}))
    client = api()
    _ = client._request(endpoint())
    _ = client._request(endpoint())
    assert "cookie" not in seen[1].headers
    assert len(client.http.cookies) == 0


# ---------------------------------------------------------------------------
# Connection pooling and lifecycle


@pytest.fixture
def keep_alive_server() -> Iterator[tuple[str, dict[str, int]]]:
    state = {"connections": 0}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def setup(self) -> None:
            state["connections"] += 1
            super().setup()

        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "2")
            self.end_headers()
            _ = self.wfile.write(b"{}")

        def log_message(self, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", state
    finally:
        server.shutdown()
        server.server_close()


def test_one_pooled_client_per_notte_client(keep_alive_server: tuple[str, dict[str, int]]) -> None:
    url, state = keep_alive_server
    client = NotteClient(api_key="test-key", server_url=url)
    assert client.sessions.http is client.personas.http is client.functions.http
    for resource in (client.sessions, client.personas, client.vaults):
        _ = resource._request(endpoint())
    assert state["connections"] == 1
    pooled = client.sessions.http
    client.close()
    assert pooled.is_closed
    # A closed client reconnects on its next request.
    _ = client.sessions._request(endpoint())
    assert client.sessions.http is not pooled
    assert state["connections"] == 2
    with client:
        _ = client.sessions._request(endpoint())
    assert client.sessions.http is not pooled


def test_connections_close_when_the_client_is_collected() -> None:
    client = NotteClient(api_key="test-key", server_url=SERVER)
    pooled = client.sessions.http
    del client
    _ = gc.collect()
    assert pooled.is_closed


def test_forked_process_gets_its_own_connections(monkeypatch: pytest.MonkeyPatch) -> None:
    client = NotteClient(api_key="test-key", server_url=SERVER)
    parent = client.sessions.http
    with patch("notte_sdk._transport.os.getpid", return_value=-1):
        child = client.sessions.http
        assert child is not parent
        client.close()
        assert child.is_closed
    # The child never closes the parent's connections.
    assert not parent.is_closed
    parent.close()


def test_streamed_responses_are_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    closed = []

    class Body(httpx.SyncByteStream):
        def __iter__(self) -> Iterator[bytes]:
            yield b"x"

        def close(self) -> None:
            closed.append(True)

    with http_client() as client:
        client._transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=Body()))
        with pytest.raises(RuntimeError):
            with stream(client, client.build_request("GET", SERVER)):
                raise RuntimeError("caller failure")
        assert closed == [True]
        assert send(client, client.build_request("GET", SERVER)).content == b"x"
        assert closed == [True, True]
