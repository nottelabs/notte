"""HTTP transport: one pooled `httpx.Client` configured like `requests`, with HTTPS recovery,
retries, streaming and object storage, and its `httpx.AsyncClient` twin for `AsyncNotteClient`.

This module and `endpoints/base.py` are the only SDK modules that use the HTTP library.
Everything else goes through the transport-neutral helpers below or `BaseClient`.

The sync and async I/O are written side by side. Every decision they make (error
translation, retry policy and delays, handshake recovery, request encoding, line
splitting, status errors) lives in one shared helper that both call.

Every HTTP failure is raised as an SDK exception from `notte_sdk.errors`, which
also subclasses the matching `requests` exception.
"""

import asyncio
import json
import os
import random
import ssl
import threading
import time
import warnings
import weakref
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Generator, Iterable, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from http.cookiejar import CookieJar
from typing import IO, Any, ParamSpec, Protocol, TypedDict, TypeVar, cast
from urllib.parse import urlencode

import anyio
import httpcore
import httpx

# Imported where it is defined: `httpcore.AnyIOBackend` is declared conditionally on anyio.
from httpcore._backends.anyio import AnyIOBackend
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


class _ClientOptions(TypedDict):
    trust_env: bool
    limits: httpx.Limits
    timeout: None
    follow_redirects: bool
    max_redirects: int


# trust_env applies HTTP(S)_PROXY, ALL_PROXY and NO_PROXY, as in requests.
# No default timeout: like requests, every call passes its own.
_CLIENT_OPTIONS = _ClientOptions(
    trust_env=True, limits=_LIMITS, timeout=None, follow_redirects=True, max_redirects=MAX_REDIRECTS
)


class _RetryRequest(Protocol):
    @property
    def method(self) -> str: ...

    @property
    def path(self) -> str: ...

    @property
    def files(self) -> Any: ...


# Delays before the second and third handshake attempts (plus up to 0.1 s of jitter).
_HANDSHAKE_DELAYS = (0.25, 0.75)


def _dropped_handshake(error: httpcore.ConnectError) -> bool:
    """Whether the server closed or reset the connection during the TLS handshake.

    anyio, the async transport's network layer, reports a TLS EOF as `EndOfStream`.
    """
    return isinstance(root_cause(error), (ssl.SSLEOFError, ConnectionResetError, anyio.EndOfStream))


def _handshake_retry_delay(host: str, attempt: int, started: float, error: httpcore.ConnectError) -> float | None:
    """Log a dropped handshake and return the delay before reconnecting, or `None` once exhausted."""
    exhausted = attempt == len(_HANDSHAKE_DELAYS)
    logger.warning(
        "HTTPS handshake {} host={} attempt={} elapsed_ms={:.0f} error_type={}",
        "exhausted" if exhausted else "retry",
        host,
        attempt + 1,
        (time.monotonic() - started) * 1000,
        type(root_cause(error)).__name__,
    )
    return None if exhausted else _HANDSHAKE_DELAYS[attempt] + random.uniform(0, 0.1)


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
        attempt = 0
        while True:
            try:
                # Only the handshake runs here: HTTP bytes are written after it returns.
                # Never retry errors around request writes or response reads.
                return self._stream.start_tls(ssl_context, server_hostname, timeout)
            except httpcore.ConnectError as exc:
                if not _dropped_handshake(exc):
                    raise
                self._stream.close()
                delay = _handshake_retry_delay(self._host, attempt, started, exc)
                if delay is None:
                    raise
                time.sleep(delay)
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


def _call_cookies() -> httpx.Cookies:
    # The current call's jar; outside a call, an empty one that nothing keeps.
    jar = _CALL_COOKIES.get()
    return httpx.Cookies() if jar is None else jar


_NO_CLIENT_COOKIES = "The SDK HTTP client keeps no cookies between calls"


@final
class _Client(httpx.Client):
    def __init__(self, *, verify: ssl.SSLContext) -> None:
        super().__init__(verify=verify, **_CLIENT_OPTIONS)
        # Replace only the default transport. Environment proxies are mounted
        # separately and keep httpx's own transports.
        self._transport.close()
        self._transport = _HandshakeTransport(verify=verify, limits=_LIMITS)

    @property
    @override
    def cookies(self) -> httpx.Cookies:
        return _call_cookies()

    @cookies.setter
    @override
    def cookies(
        self,
        cookies: httpx.Cookies | CookieJar | dict[str, str] | list[tuple[str, str]],  # pyright: ignore[reportPropertyTypeMismatch]
    ) -> None:
        raise TypeError(_NO_CLIENT_COOKIES)

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


_SHARED_CLIENTS: "weakref.WeakSet[SharedHttpClient | AsyncSharedHttpClient]" = weakref.WeakSet()


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
    cause = root_cause(error)
    # Under the async transport, anyio reports a TLS EOF during the handshake as `EndOfStream`.
    if isinstance(cause, (ssl.SSLError, anyio.EndOfStream)):
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


def _status_error(response: httpx.Response) -> NotteHTTPStatusError | None:
    """`NotteHTTPStatusError` for a 4xx or 5xx status, with requests' message."""
    if 400 <= response.status_code < 500:
        kind = "Client Error"
    elif 500 <= response.status_code < 600:
        kind = "Server Error"
    else:
        return None
    return NotteHTTPStatusError(
        f"{response.status_code} {kind}: {response.reason_phrase} for url: {response.url}",
        response=response,
        request=response.request,
    )


def raise_for_status(response: httpx.Response) -> None:
    """Raise `NotteHTTPStatusError` for a 4xx or 5xx status, with requests' message."""
    error = _status_error(response)
    if error is None:
        return
    # A streamed response closes when its block exits. Read the error body first so callers
    # can still use `error.response.text` and `json()`, as requests left them readable.
    try:
        _ = response.read()
    except httpx.HTTPError:
        pass  # the status error is more useful than the failure to read its body
    raise error


def decode_json(response: httpx.Response) -> Any:
    """Parse a JSON body; invalid JSON raises `NotteJSONDecodeError`, as requests raised its own."""
    try:
        return response.json()
    except json.JSONDecodeError as e:
        raise NotteJSONDecodeError(e.msg, e.doc, e.pos) from e


class _LineSplitter:
    """Split a streamed body into lines exactly as `requests.Response.iter_lines` does."""

    def __init__(self) -> None:
        self._pending: bytes | None = None

    def feed(self, chunk: bytes) -> list[bytes]:
        """The lines completed by `chunk`; a trailing partial line waits for the next chunk."""
        if self._pending is not None:
            chunk = self._pending + chunk
        lines = chunk.splitlines()
        if lines and lines[-1] and chunk and lines[-1][-1] == chunk[-1]:
            self._pending = lines.pop()
        else:
            self._pending = None
        return lines

    def end(self) -> list[bytes]:
        """The last line, when the body did not end with a line break."""
        return [] if self._pending is None else [self._pending]


def iter_lines(response: httpx.Response) -> Iterator[bytes]:
    """Split a streamed body into lines exactly as `requests.Response.iter_lines` does."""
    lines = _LineSplitter()
    for chunk in response.iter_bytes():
        yield from lines.feed(chunk)
    yield from lines.end()


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


class _RetryBudget:
    """The retry decisions for one request, within one request time budget.

    `send_with_retries` and `asend_with_retries` only send, close and sleep; this decides.
    """

    def __init__(self, endpoint: _RetryRequest, *, max_retries: int, timeout: float) -> None:
        self._endpoint: _RetryRequest = endpoint
        self._max_retries: int = max(0, max_retries)
        self._timeout: float = timeout
        self._deadline: float = time.monotonic() + timeout
        self._positions: list[tuple[Any, int]] | None = _upload_positions(endpoint)
        self._attempt: int = 0

    def remaining(self) -> float:
        """The time budget for the next attempt; raises once the request's budget is spent."""
        remaining = self._timeout if self._attempt == 0 else self._deadline - time.monotonic()
        if remaining <= 0:
            raise NotteRequestTimeoutError("SDK request retry deadline exceeded")
        return remaining

    def after_error(self, error: NotteRequestError) -> float | None:
        """The delay before retrying a failed attempt, or `None` to raise its error."""
        # Uploaded files are rewound before a retry; one that cannot be is not resent.
        if not (
            self._can_retry()
            and is_retryable_exception(error, self._endpoint.method)
            and _rewind_files(self._positions)
        ):
            return None
        delay = backoff_delay(self._attempt)
        if time.monotonic() + delay >= self._deadline:
            return None
        return self._retrying(delay, type(error).__name__)

    def after_response(self, response: httpx.Response) -> float | None:
        """The delay before retrying a response (the caller closes it), or `None` to return it."""
        if not (self._can_retry() and is_retryable_status(response.status_code, self._endpoint.method)):
            return None
        delay = retry_delay(self._attempt, response.headers.get("Retry-After"))
        if delay is None or time.monotonic() + delay >= self._deadline or not _rewind_files(self._positions):
            return None
        return self._retrying(delay, f"status {response.status_code}")

    def _can_retry(self) -> bool:
        return self._attempt < self._max_retries

    def _retrying(self, delay: float, reason: str) -> float:
        self._attempt += 1
        logger.warning(
            f"`{self._endpoint.method} {self._endpoint.path}` failed ({reason}), retrying in {delay:.1f}s ({self._attempt}/{self._max_retries})"
        )
        return delay


def send_with_retries(
    endpoint: _RetryRequest, send: Callable[[float], httpx.Response], *, max_retries: int, timeout: float
) -> httpx.Response:
    """Retry transient responses and replayable uploads within one request time budget."""
    budget = _RetryBudget(endpoint, max_retries=max_retries, timeout=timeout)
    while True:
        remaining = budget.remaining()
        try:
            response = send(remaining)
        except NotteRequestError as e:
            delay = budget.after_error(e)
            if delay is None:
                raise
        else:
            delay = budget.after_response(response)
            if delay is None:
                return response
            response.close()
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
# `aget_text`, `aput_object` and `aget_object` below are their async twins, under the same rules.


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


# ---------------------------------------------------------------------------
# Async transport: the same client configuration, handshake recovery and retries on
# `httpx.AsyncClient`. Each function below mirrors the sync one of the same name without
# its `a` prefix and shares its decisions through the helpers above.


class _AsyncHandshakeStream(httpcore.AsyncNetworkStream):
    """A TCP stream that reconnects when the server drops the TLS handshake."""

    def __init__(
        self,
        connect: Callable[[], Awaitable[httpcore.AsyncNetworkStream]],
        host: str,
        stream: httpcore.AsyncNetworkStream,
    ) -> None:
        self._connect: Callable[[], Awaitable[httpcore.AsyncNetworkStream]] = connect
        self._host: str = host
        self._stream: httpcore.AsyncNetworkStream = stream

    @override
    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return await self._stream.read(max_bytes, timeout)

    @override
    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        await self._stream.write(buffer, timeout)

    @override
    async def aclose(self) -> None:
        await self._stream.aclose()

    @override
    def get_extra_info(self, info: str) -> Any:
        return self._stream.get_extra_info(info)

    @override
    async def start_tls(
        self, ssl_context: ssl.SSLContext, server_hostname: str | None = None, timeout: float | None = None
    ) -> httpcore.AsyncNetworkStream:
        started = time.monotonic()
        attempt = 0
        while True:
            try:
                # Only the handshake runs here: HTTP bytes are written after it returns.
                # Never retry errors around request writes or response reads.
                return await self._stream.start_tls(ssl_context, server_hostname, timeout)
            except httpcore.ConnectError as exc:
                if not _dropped_handshake(exc):
                    raise
                await self._stream.aclose()
                delay = _handshake_retry_delay(self._host, attempt, started, exc)
                if delay is None:
                    raise
                await asyncio.sleep(delay)
                attempt += 1
                # The caller's connect timeout applies to each attempt.
                self._stream = await self._connect()


class _AsyncHandshakeBackend(httpcore.AsyncNetworkBackend):
    def __init__(self) -> None:
        self._backend: AnyIOBackend = AnyIOBackend()

    @override
    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        options = None if socket_options is None else list(socket_options)

        def connect() -> Awaitable[httpcore.AsyncNetworkStream]:
            return self._backend.connect_tcp(host, port, timeout, local_address, options)

        return _AsyncHandshakeStream(connect, host, await connect())

    @override
    async def connect_unix_socket(
        self, path: str, timeout: float | None = None, socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None
    ) -> httpcore.AsyncNetworkStream:
        return await self._backend.connect_unix_socket(path, timeout, socket_options)

    @override
    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


@final
class _AsyncHandshakeTransport(httpx.AsyncHTTPTransport):
    """Direct connections only: proxied connections keep httpx's normal behavior."""

    def __init__(self, *, verify: ssl.SSLContext, limits: httpx.Limits) -> None:
        super().__init__(verify=verify, limits=limits)
        # The pool httpx builds for direct connections, with the handshake-retrying backend.
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=verify,
            max_connections=limits.max_connections,
            max_keepalive_connections=limits.max_keepalive_connections,
            keepalive_expiry=limits.keepalive_expiry,
            network_backend=_AsyncHandshakeBackend(),
        )


@final
class _AsyncClient(httpx.AsyncClient):
    def __init__(self, *, verify: ssl.SSLContext) -> None:
        super().__init__(verify=verify, **_CLIENT_OPTIONS)
        # The default transport has opened nothing yet, so it needs no closing.
        self._transport = _AsyncHandshakeTransport(verify=verify, limits=_LIMITS)

    @property
    @override
    def cookies(self) -> httpx.Cookies:
        return _call_cookies()

    @cookies.setter
    @override
    def cookies(
        self,
        cookies: httpx.Cookies | CookieJar | dict[str, str] | list[tuple[str, str]],  # pyright: ignore[reportPropertyTypeMismatch]
    ) -> None:
        raise TypeError(_NO_CLIENT_COOKIES)

    @override
    def build_request(self, method: str, url: httpx.URL | str, **options: Any) -> httpx.Request:
        # A malformed URL fails here, before send(); raise it as an SDK exception too.
        with translate_errors():
            return super().build_request(method, url, **options)


def async_http_client() -> httpx.AsyncClient:
    """The async twin of `http_client()`, with the same configuration and handshake recovery."""
    return _AsyncClient(verify=_ssl_context())


_OTHER_LOOP = (
    "This AsyncNotteClient's connections belong to another event loop that is still open. "
    "Use the client from that loop, create one client per event loop, "
    "or `await client.aclose()` in that loop first."
)


class AsyncSharedHttpClient:
    """One pooled async client per `AsyncNotteClient`, opened on first use.

    httpx async connections belong to the event loop that opened them. Using them from another
    open loop raises `RuntimeError` instead of hanging; once their loop is closed, they can
    never be used again, so the next request opens new ones in the current loop.
    """

    def __init__(self) -> None:
        # Event loops in different threads can share one client: the lock makes the ownership
        # check and pool creation one step. Nothing awaits while it is held.
        self._lock: threading.Lock = threading.Lock()
        self._client: httpx.AsyncClient | None = None
        self._pid: int | None = None
        self._loop: weakref.ref[asyncio.AbstractEventLoop] | None = None
        _SHARED_CLIENTS.add(self)

    def _after_fork_in_child(self) -> None:
        # A thread that held the lock during fork does not exist in the child.
        self._lock = threading.Lock()

    def _owner_loop(self) -> asyncio.AbstractEventLoop | None:
        """The open event loop the current connections belong to, if any."""
        loop = None if self._loop is None else self._loop()
        return None if loop is None or loop.is_closed() else loop

    def get(self) -> httpx.AsyncClient:
        loop = asyncio.get_running_loop()
        with self._lock:
            # A forked child must not share the parent's TLS connections.
            if self._client is not None and self._pid == os.getpid():
                owner = self._owner_loop()
                if owner is loop:
                    return self._client
                if owner is not None:
                    raise RuntimeError(_OTHER_LOOP)
            self._client = async_http_client()
            self._pid = os.getpid()
            self._loop = weakref.ref(loop)
            return self._client

    async def aclose(self) -> None:
        """Close pooled connections. A later request opens a new client."""
        with self._lock:
            if self._client is None:
                return
            owned = self._pid == os.getpid()
            owner = self._owner_loop()
            if owned and owner is not None and owner is not asyncio.get_running_loop():
                raise RuntimeError(_OTHER_LOOP)
            client, self._client = self._client, None
        # A child never closes its parent's connections; nothing can close those of a closed loop.
        if owned and owner is not None:
            await client.aclose()

    def warn_unclosed(self) -> None:
        """Finalizer: async connections cannot be closed during garbage collection."""
        if self._client is not None and self._pid == os.getpid():
            warnings.warn(
                (
                    "An AsyncNotteClient was garbage collected with open connections. "
                    "Use `async with AsyncNotteClient() as client:` or `await client.aclose()`."
                ),
                ResourceWarning,
                stacklevel=1,
            )


@asynccontextmanager
async def astream(
    client: httpx.AsyncClient, request: httpx.Request, *, follow_redirects: bool = True
) -> AsyncGenerator[httpx.Response]:
    """Send a request and yield the response before its body is read; always closes it."""
    token = _CALL_COOKIES.set(httpx.Cookies())
    try:
        response = await client.send(request, stream=True, follow_redirects=follow_redirects)
    except (httpx.HTTPError, httpx.InvalidURL) as error:
        raise translate_error(error) from error
    finally:
        _CALL_COOKIES.reset(token)
    try:
        with translate_errors(body=True):
            yield response
    finally:
        await response.aclose()


async def asend(client: httpx.AsyncClient, request: httpx.Request, *, follow_redirects: bool = True) -> httpx.Response:
    """Send a request and read its whole body, as `requests` does without `stream=True`."""
    async with astream(client, request, follow_redirects=follow_redirects) as response:
        _ = await response.aread()
    return response


async def araise_for_status(response: httpx.Response) -> None:
    """Raise `NotteHTTPStatusError` for a 4xx or 5xx status, with requests' message."""
    error = _status_error(response)
    if error is None:
        return
    # Read the error body before the streamed response closes, as `raise_for_status` does.
    try:
        _ = await response.aread()
    except httpx.HTTPError:
        pass  # the status error is more useful than the failure to read its body
    raise error


async def aiter_lines(response: httpx.Response) -> AsyncIterator[bytes]:
    """Split a streamed body into lines exactly as `requests.Response.iter_lines` does."""
    lines = _LineSplitter()
    async for chunk in response.aiter_bytes():
        for line in lines.feed(chunk):
            yield line
    for line in lines.end():
        yield line


_P = ParamSpec("_P")
_T = TypeVar("_T")


async def _until_done(task: "asyncio.Future[_T]") -> asyncio.CancelledError | None:
    """Wait for `task` even if the caller is cancelled meanwhile; returns that cancellation."""
    cancelled: asyncio.CancelledError | None = None
    while not task.done():
        try:
            _ = await asyncio.wait({task})
        except asyncio.CancelledError as error:
            cancelled = error
    return cancelled


async def athread_owned(
    release: Callable[[_T], object], func: Callable[_P, _T], /, *args: _P.args, **kwargs: _P.kwargs
) -> _T:
    """`asyncio.to_thread(func, ...)` for a call that creates a file or opens a handle.

    Cancelling `to_thread` does not stop its worker, whose result would then be lost: a created
    file stays on disk, a handle stays open. When the caller is cancelled, this waits for the
    worker, passes its result to `release` (in a thread) and re-raises the cancellation.
    """
    task = asyncio.ensure_future(asyncio.to_thread(func, *args, **kwargs))
    cancelled = await _until_done(task)
    if cancelled is None:
        return task.result()
    if not task.cancelled() and task.exception() is None:
        await athread_finally(release, task.result())
    raise cancelled


async def athread(func: Callable[_P, _T], /, *args: _P.args, **kwargs: _P.kwargs) -> _T:
    """Run blocking work off the loop, settling it before propagating cancellation."""
    task = asyncio.ensure_future(asyncio.to_thread(func, *args, **kwargs))
    cancelled = await _until_done(task)
    error = None if task.cancelled() else task.exception()
    if cancelled is not None:
        raise cancelled
    if error is not None:
        raise error
    return task.result()


async def athread_finally(func: Callable[_P, object], /, *args: _P.args, **kwargs: _P.kwargs) -> None:
    """`asyncio.to_thread(func, ...)` for cleanup: it completes even if the caller is cancelled
    again meanwhile, and that cancellation is re-raised after it."""
    _ = await athread(func, *args, **kwargs)


async def awrite_chunks(chunks: AsyncIterator[bytes], output: IO[bytes]) -> None:
    """Write a streamed body to a local file, each write in a worker thread, off the event loop."""
    async for chunk in chunks:
        _ = await asyncio.to_thread(output.write, chunk)


async def _aopen_client() -> httpx.AsyncClient:
    """A new client for one call (object storage, public downloads), built in a worker thread:
    its SSL context reads the CA bundle from disk.

    The pooled client of `AsyncSharedHttpClient` is built on the loop instead, once per
    `AsyncNotteClient` and event loop: its lock cannot be held across an await.
    """
    return await asyncio.to_thread(async_http_client)


async def aget_text(url: str, *, timeout: float) -> str:
    """The async twin of `get_text`."""
    async with await _aopen_client() as client:
        response = await asend(client, client.build_request("GET", url, timeout=timeout))
    await araise_for_status(response)
    return response.text


# Read size for streamed storage uploads, as httpx reads a file body.
_UPLOAD_CHUNK_SIZE = 64 * 1024


def _remaining_length(payload: IO[bytes]) -> int:
    start = payload.tell()
    size = payload.seek(0, os.SEEK_END) - start
    _ = payload.seek(start)
    return size


async def _aread_chunks(payload: IO[bytes]) -> AsyncIterator[bytes]:
    while chunk := await asyncio.to_thread(payload.read, _UPLOAD_CHUNK_SIZE):
        yield chunk


async def aput_object(url: str, payload: IO[bytes], *, headers: Mapping[str, str], timeout: tuple[float, float]) -> int:
    """The async twin of `put_object`. `payload` is read in a worker thread, never on the event loop.

    httpx reads a file body synchronously, so the payload is streamed from an async iterator
    instead. Its length is sent as `Content-Length`, as httpx sends a file's: presigned storage
    URLs reject chunked uploads.
    """
    size = await asyncio.to_thread(_remaining_length, payload)
    request_headers = httpx.Headers(headers)
    if "Content-Length" not in request_headers:
        request_headers["Content-Length"] = str(size)
    async with await _aopen_client() as storage_session:
        request = storage_session.build_request(
            "PUT", url, content=_aread_chunks(payload), headers=request_headers, timeout=_storage_timeout(timeout)
        )
        async with astream(storage_session, request, follow_redirects=False) as response:
            _ = await response.aread()
            await araise_for_status(response)
            return response.status_code


@asynccontextmanager
async def aget_object(
    url: str, *, timeout: tuple[float, float], chunk_size: int
) -> AsyncGenerator[tuple[int, AsyncIterator[bytes]]]:
    """The async twin of `get_object`: yields the response status (2xx) and the body's chunks."""
    async with await _aopen_client() as storage_session:
        request = storage_session.build_request("GET", url, timeout=_storage_timeout(timeout))
        async with astream(storage_session, request, follow_redirects=False) as response:
            await araise_for_status(response)
            yield response.status_code, response.aiter_bytes(chunk_size=chunk_size)


async def asend_with_retries(
    endpoint: _RetryRequest,
    send: Callable[[float], Awaitable[httpx.Response]],
    *,
    max_retries: int,
    timeout: float,
) -> httpx.Response:
    """Retry transient responses and replayable uploads within one request time budget."""
    budget = _RetryBudget(endpoint, max_retries=max_retries, timeout=timeout)
    while True:
        remaining = budget.remaining()
        try:
            response = await send(remaining)
        except NotteRequestError as e:
            delay = budget.after_error(e)
            if delay is None:
                raise
        else:
            delay = budget.after_response(response)
            if delay is None:
                return response
            await response.aclose()
        await asyncio.sleep(delay)
