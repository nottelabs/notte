"""HTTP transport: one pooled `httpx.Client` configured like `requests`, with HTTPS recovery,
retries, streaming and object storage.

This module and `endpoints/base.py` are the only SDK modules that use the HTTP library.
Everything else goes through the transport-neutral helpers below or `BaseClient`.

Every HTTP failure is raised as an SDK exception from `notte_sdk.errors`, which
also subclasses the matching `requests` exception.
"""

import json
import os
import random
import ssl
import threading
import time
import weakref
from collections.abc import Callable, Generator, Iterable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from http.cookiejar import CookieJar
from typing import IO, Any, Protocol, cast
from urllib.parse import urlencode

import httpcore
import httpx
from notte_core.logging import logger
from typing_extensions import final, override

from notte_sdk._retry import backoff_delay, is_retryable_exception, is_retryable_status, retry_delay, root_cause
from notte_sdk.errors import (
    NotteConnectionError,
    NotteConnectTimeoutError,
    NotteHTTPStatusError,
    NotteInvalidURLError,
    NotteJSONDecodeError,
    NotteProxyError,
    NotteReadTimeoutError,
    NotteRequestError,
    NotteRequestTimeoutError,
    NotteSSLError,
    NotteStreamError,
    NotteTooManyRedirectsError,
)

# requests' redirect limit (httpx defaults to 20).
MAX_REDIRECTS = 30
# requests opened a connection per call, so concurrency was never capped; keep
# at most 20 idle connections, closed after 5 s idle so the server never does it first.
_LIMITS = httpx.Limits(max_connections=None, max_keepalive_connections=20, keepalive_expiry=5.0)
# requests opened a new session per call: cookies set during a call's redirects were sent on
# its later hops, and none outlived the call. `stream()` gives every call its own jar.
_CALL_COOKIES: ContextVar[httpx.Cookies | None] = ContextVar("notte_sdk_call_cookies", default=None)


class _RetryRequest(Protocol):
    @property
    def method(self) -> str: ...

    @property
    def path(self) -> str: ...

    @property
    def files(self) -> Any: ...


class _HandshakeStream(httpcore.NetworkStream):
    """A TCP stream that reconnects when the server drops the TLS handshake."""

    def __init__(self, connect: Callable[[], httpcore.NetworkStream], host: str) -> None:
        self._connect: Callable[[], httpcore.NetworkStream] = connect
        self._host: str = host
        self._stream: httpcore.NetworkStream = connect()

    @override
    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return self._stream.read(max_bytes, timeout)

    @override
    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self._stream.write(buffer, timeout)

    @override
    def close(self) -> None:
        self._stream.close()

    @override
    def get_extra_info(self, info: str) -> Any:
        return self._stream.get_extra_info(info)

    @override
    def start_tls(
        self, ssl_context: ssl.SSLContext, server_hostname: str | None = None, timeout: float | None = None
    ) -> httpcore.NetworkStream:
        started = time.monotonic()
        delays = (0.25, 0.75)
        attempt = 0
        while True:
            try:
                # Only the handshake runs here: HTTP bytes are written after it returns.
                # Never retry errors around request writes or response reads.
                return self._stream.start_tls(ssl_context, server_hostname, timeout)
            except httpcore.ConnectError as exc:
                cause = root_cause(exc)
                if not isinstance(cause, (ssl.SSLEOFError, ConnectionResetError)):
                    raise
                self._stream.close()
                exhausted = attempt == len(delays)
                logger.warning(
                    "HTTPS handshake {} host={} attempt={} elapsed_ms={:.0f} error_type={}",
                    "exhausted" if exhausted else "retry",
                    self._host,
                    attempt + 1,
                    (time.monotonic() - started) * 1000,
                    type(cause).__name__,
                )
                if exhausted:
                    raise
                time.sleep(delays[attempt] + random.uniform(0, 0.1))
                attempt += 1
                # The caller's connect timeout applies to each attempt.
                self._stream = self._connect()


class _HandshakeBackend(httpcore.NetworkBackend):
    def __init__(self) -> None:
        self._backend: httpcore.SyncBackend = httpcore.SyncBackend()

    @override
    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        options = None if socket_options is None else list(socket_options)
        return _HandshakeStream(
            lambda: self._backend.connect_tcp(host, port, timeout, local_address, options),
            host,
        )

    @override
    def connect_unix_socket(
        self, path: str, timeout: float | None = None, socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None
    ) -> httpcore.NetworkStream:
        return self._backend.connect_unix_socket(path, timeout, socket_options)

    @override
    def sleep(self, seconds: float) -> None:
        self._backend.sleep(seconds)


@final
class _HandshakeTransport(httpx.HTTPTransport):
    """Direct connections only: proxied connections keep httpx's normal behavior."""

    def __init__(self, *, verify: ssl.SSLContext, limits: httpx.Limits) -> None:
        super().__init__(verify=verify, limits=limits)
        # The pool httpx builds for direct connections, with the handshake-retrying backend.
        self._pool = httpcore.ConnectionPool(
            ssl_context=verify,
            max_connections=limits.max_connections,
            max_keepalive_connections=limits.max_keepalive_connections,
            keepalive_expiry=limits.keepalive_expiry,
            network_backend=_HandshakeBackend(),
        )


@final
class _Client(httpx.Client):
    def __init__(self, *, verify: ssl.SSLContext) -> None:
        # trust_env applies HTTP(S)_PROXY, ALL_PROXY and NO_PROXY, as in requests.
        # No default timeout: like requests, every call passes its own.
        super().__init__(
            verify=verify,
            trust_env=True,
            limits=_LIMITS,
            timeout=None,
            follow_redirects=True,
            max_redirects=MAX_REDIRECTS,
        )
        # Replace only the default transport. Environment proxies are mounted
        # separately and keep httpx's own transports.
        self._transport.close()
        self._transport = _HandshakeTransport(verify=verify, limits=_LIMITS)

    @property
    @override
    def cookies(self) -> httpx.Cookies:
        # The current call's jar; outside a call, an empty one that nothing keeps.
        jar = _CALL_COOKIES.get()
        return httpx.Cookies() if jar is None else jar

    @cookies.setter
    @override
    def cookies(
        self,
        cookies: httpx.Cookies | CookieJar | dict[str, str] | list[tuple[str, str]],  # pyright: ignore[reportPropertyTypeMismatch]
    ) -> None:
        raise TypeError("The SDK HTTP client keeps no cookies between calls")

    @override
    def build_request(self, method: str, url: httpx.URL | str, **options: Any) -> httpx.Request:
        # A malformed URL fails here, before send(); raise it as an SDK exception too.
        with translate_errors():
            return super().build_request(method, url, **options)


def _ssl_context() -> ssl.SSLContext:
    """CA certificates as requests chooses them: `REQUESTS_CA_BUNDLE`, then `CURL_CA_BUNDLE`, then certifi."""
    bundle = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("CURL_CA_BUNDLE")
    if not bundle:
        # certifi, ignoring SSL_CERT_FILE and SSL_CERT_DIR as requests does.
        return httpx.create_ssl_context(trust_env=False)
    if os.path.isdir(bundle):
        return ssl.create_default_context(capath=bundle)
    return ssl.create_default_context(cafile=bundle)


def http_client() -> httpx.Client:
    """Create a client that behaves like `requests`: redirects, proxies and CA settings.

    Only direct HTTPS EOF/reset failures during the TLS handshake get up to
    three attempts. The caller's timeout applies to each connection attempt.
    HTTP responses and failures after transmission never trigger retries here.
    Environment settings are read when the client is created.
    """
    return _Client(verify=_ssl_context())


class SharedHttpClient:
    """One pooled client per `NotteClient`, opened on first use."""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._client: httpx.Client | None = None
        self._pid: int | None = None
        _SHARED_CLIENTS.add(self)

    def _after_fork_in_child(self) -> None:
        # A thread that held the lock during fork does not exist in the child.
        self._lock = threading.Lock()

    def get(self) -> httpx.Client:
        with self._lock:
            # A forked child must not share the parent's TLS connections.
            if self._client is None or self._pid != os.getpid():
                self._client = http_client()
                self._pid = os.getpid()
            return self._client

    def close(self) -> None:
        """Close pooled connections. A later request opens a new client."""
        with self._lock:
            client, self._client = self._client, None
            owned = self._pid == os.getpid()
        if client is not None and owned:
            client.close()


_SHARED_CLIENTS: "weakref.WeakSet[SharedHttpClient]" = weakref.WeakSet()


def _reset_shared_clients_after_fork() -> None:
    for shared in list(_SHARED_CLIENTS):
        shared._after_fork_in_child()  # pyright: ignore[reportPrivateUsage]


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_shared_clients_after_fork)


def translate_error(error: Exception, *, body: bool = False) -> NotteRequestError:
    """Map an httpx failure to the SDK exception matching what `requests` raised.

    `body` marks failures while reading a response body, after its headers arrived.
    """
    message = str(error) or type(error).__name__
    if isinstance(root_cause(error), ssl.SSLError):
        return NotteSSLError(message)
    if isinstance(error, (httpx.ConnectTimeout, httpx.PoolTimeout)):
        return NotteConnectTimeoutError(message)
    if isinstance(error, httpx.ReadTimeout):
        return NotteReadTimeoutError(message)
    if isinstance(error, httpx.TimeoutException):
        return NotteRequestTimeoutError(message)
    if body and isinstance(error, httpx.TransportError):
        return NotteStreamError(message)
    if isinstance(error, httpx.ProxyError):
        return NotteProxyError(message)
    if isinstance(error, (httpx.NetworkError, httpx.RemoteProtocolError)):
        return NotteConnectionError(message)
    if isinstance(error, httpx.TooManyRedirects):
        return NotteTooManyRedirectsError(message)
    if isinstance(error, (httpx.UnsupportedProtocol, httpx.InvalidURL)):
        return NotteInvalidURLError(message)
    return NotteRequestError(message)


@contextmanager
def translate_errors(*, body: bool = False) -> Generator[None]:
    """Raise httpx failures inside the block as SDK exceptions."""
    try:
        yield
    except (httpx.HTTPError, httpx.InvalidURL) as error:
        raise translate_error(error, body=body) from error


@contextmanager
def stream(client: httpx.Client, request: httpx.Request, *, follow_redirects: bool = True) -> Generator[httpx.Response]:
    """Send a request and yield the response before its body is read; always closes it."""
    token = _CALL_COOKIES.set(httpx.Cookies())
    try:
        response = client.send(request, stream=True, follow_redirects=follow_redirects)
    except (httpx.HTTPError, httpx.InvalidURL) as error:
        raise translate_error(error) from error
    finally:
        _CALL_COOKIES.reset(token)
    try:
        with translate_errors(body=True):
            yield response
    finally:
        response.close()


def send(client: httpx.Client, request: httpx.Request, *, follow_redirects: bool = True) -> httpx.Response:
    """Send a request and read its whole body, as `requests` does without `stream=True`."""
    with stream(client, request, follow_redirects=follow_redirects) as response:
        _ = response.read()
    return response


def raise_for_status(response: httpx.Response) -> None:
    """Raise `NotteHTTPStatusError` for a 4xx or 5xx status, with requests' message."""
    if 400 <= response.status_code < 500:
        kind = "Client Error"
    elif 500 <= response.status_code < 600:
        kind = "Server Error"
    else:
        return
    # A streamed response closes when its block exits. Read the error body first so callers
    # can still use `error.response.text` and `json()`, as requests left them readable.
    try:
        _ = response.read()
    except httpx.HTTPError:
        pass  # the status error is more useful than the failure to read its body
    raise NotteHTTPStatusError(
        f"{response.status_code} {kind}: {response.reason_phrase} for url: {response.url}",
        response=response,
        request=response.request,
    )


def decode_json(response: httpx.Response) -> Any:
    """Parse a JSON body; invalid JSON raises `NotteJSONDecodeError`, as requests raised its own."""
    try:
        return response.json()
    except json.JSONDecodeError as e:
        raise NotteJSONDecodeError(e.msg, e.doc, e.pos) from e


def iter_lines(response: httpx.Response) -> Iterator[bytes]:
    """Split a streamed body into lines exactly as `requests.Response.iter_lines` does."""
    pending: bytes | None = None
    for chunk in response.iter_bytes():
        if pending is not None:
            chunk = pending + chunk
        lines = chunk.splitlines()
        if lines and lines[-1] and chunk and lines[-1][-1] == chunk[-1]:
            pending = lines.pop()
        else:
            pending = None
        yield from lines
    if pending is not None:
        yield pending


def _as_values(value: Any) -> list[Any]:
    # requests sends each item of an iterable value (a list, or a dict's keys) as its own field.
    if isinstance(value, (str, bytes)) or not hasattr(value, "__iter__"):
        return [value]
    return list(cast(Iterable[Any], value))


def with_query(url: str, params: Mapping[str, Any] | None) -> str:
    """Append query parameters encoded as requests encodes them (`True`, not `true`)."""
    if not params:
        return url
    pairs = [(key, value) for key, values in params.items() for value in _as_values(values) if value is not None]
    query = urlencode(pairs, doseq=True)
    if not query:
        return url
    return f"{url}&{query}" if "?" in url else f"{url}?{query}"


def form_fields(data: Mapping[str, Any]) -> dict[str, list[str | bytes]]:
    """Multipart form fields as requests builds them: `str()` of each value, `None` skipped."""
    fields: dict[str, list[str | bytes]] = {}
    for key, values in data.items():
        for value in _as_values(values):
            if value is not None:
                fields.setdefault(key, []).append(value if isinstance(value, bytes) else str(value))
    return fields


def multipart_files(files: Any) -> dict[str, Any]:
    """Upload parts for httpx; a bare file is named as requests names it."""
    uploads = cast(dict[str, Any], files if isinstance(files, dict) else vars(files))
    parts: dict[str, Any] = {}
    for key, value in uploads.items():
        if isinstance(value, (tuple, list)):
            parts[key] = tuple(cast(Iterable[Any], value))
            continue
        name = getattr(value, "name", None)
        if isinstance(name, str) and name and name[0] != "<" and name[-1] != ">":
            parts[key] = (os.path.basename(name), value)
        else:
            parts[key] = (key, value)
    return parts


def send_with_retries(
    endpoint: _RetryRequest, send: Callable[[float], httpx.Response], *, max_retries: int, timeout: float
) -> httpx.Response:
    """Retry transient responses and replayable uploads within one request time budget."""
    max_retries = max(0, max_retries)
    deadline = time.monotonic() + timeout
    positions = _upload_positions(endpoint)
    attempt = 0
    while True:
        # Uploaded files are rewound before a retry; one that cannot be is not resent.
        can_retry = attempt < max_retries
        remaining = timeout if attempt == 0 else deadline - time.monotonic()
        if remaining <= 0:
            raise NotteRequestTimeoutError("SDK request retry deadline exceeded")
        try:
            response = send(remaining)
        except NotteRequestError as e:
            if not (can_retry and is_retryable_exception(e, endpoint.method) and _rewind_files(positions)):
                raise
            delay = backoff_delay(attempt)
            if time.monotonic() + delay >= deadline:
                raise
            reason = type(e).__name__
        else:
            if not (can_retry and is_retryable_status(response.status_code, endpoint.method)):
                return response
            response_delay = retry_delay(attempt, response.headers.get("Retry-After"))
            if response_delay is None or time.monotonic() + response_delay >= deadline or not _rewind_files(positions):
                return response
            delay = response_delay
            reason = f"status {response.status_code}"
            response.close()
        attempt += 1
        logger.warning(
            f"`{endpoint.method} {endpoint.path}` failed ({reason}), retrying in {delay:.1f}s ({attempt}/{max_retries})"
        )
        time.sleep(delay)


def _upload_positions(endpoint: _RetryRequest) -> list[tuple[Any, int]] | None:
    """Remember original cursors so retries send the same bytes as the first attempt."""
    files: Any = endpoint.files
    if files is None:
        return []
    uploads = cast(dict[str, Any], files if isinstance(files, dict) else vars(files))
    positions: list[tuple[Any, int]] = []
    for handle in uploads.values():
        if isinstance(handle, tuple):
            handle = cast(Any, handle)[1]
        if isinstance(handle, (str, bytes)):
            continue
        try:
            positions.append((handle, handle.tell()))
        except (AttributeError, OSError, ValueError):
            return None
    return positions


def _rewind_files(positions: list[tuple[Any, int]] | None) -> bool:
    if positions is None:
        return False
    for handle, offset in positions:
        try:
            handle.seek(offset)
        except (AttributeError, OSError, ValueError):
            return False
    return True


# Any failure to send a request or to read its response, such as a timeout or a reset connection.
TransportError = NotteRequestError
# The request was cut short before a full response arrived: a timeout, a dropped connection
# or a truncated body. Callers that only read state can safely ask again.
INTERRUPTED_ERRORS: tuple[type[TransportError], ...] = (
    NotteRequestTimeoutError,
    NotteConnectionError,
    NotteStreamError,
)


def get_text(url: str, *, timeout: float) -> str:
    """Download a public URL (no API credentials) as text; raises `TransportError` on any failure."""
    with http_client() as client:
        response = send(client, client.build_request("GET", url, timeout=timeout))
    raise_for_status(response)
    return response.text


# Object storage URLs are presigned: they get a separate client so the API token, preview
# selector and capability headers never reach them, and their redirects are not followed.


def _storage_timeout(timeout: tuple[float, float]) -> httpx.Timeout:
    # requests' (connect, read) pair; httpx also applies the read timeout to writes and the pool.
    connect, read = timeout
    return httpx.Timeout(read, connect=connect)


def put_object(url: str, payload: IO[bytes], *, headers: Mapping[str, str], timeout: tuple[float, float]) -> int:
    """Upload `payload` to a presigned storage URL and return the response status (2xx)."""
    with http_client() as storage_session:
        request = storage_session.build_request(
            "PUT", url, content=payload, headers=dict(headers), timeout=_storage_timeout(timeout)
        )
        with stream(storage_session, request, follow_redirects=False) as response:
            _ = response.read()
            raise_for_status(response)
            return response.status_code


@contextmanager
def get_object(
    url: str, *, timeout: tuple[float, float], chunk_size: int
) -> Generator[tuple[int, Iterator[bytes]], None, None]:
    """Stream a presigned storage URL: yields the response status (2xx) and the body's chunks."""
    with http_client() as storage_session:
        request = storage_session.build_request("GET", url, timeout=_storage_timeout(timeout))
        with stream(storage_session, request, follow_redirects=False) as response:
            raise_for_status(response)
            yield response.status_code, response.iter_bytes(chunk_size=chunk_size)
