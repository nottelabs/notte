"""Request-scoped HTTPS recovery, before any application request is sent."""

import random
import ssl
import time
from collections.abc import Callable
from typing import Any, Protocol, cast

import requests
from notte_core.logging import logger
from requests.adapters import HTTPAdapter
from typing_extensions import override
from urllib3.connection import HTTPSConnection
from urllib3.connectionpool import HTTPSConnectionPool

from notte_sdk._retry import backoff_delay, is_retryable_exception, is_retryable_status, retry_delay


class _RetryRequest(Protocol):
    @property
    def method(self) -> str: ...

    @property
    def path(self) -> str: ...

    @property
    def files(self) -> Any: ...


class _HandshakeConnection(HTTPSConnection):
    @override
    def connect(self) -> None:
        # Proxy connections deliberately retain urllib3's normal behavior.
        if self.proxy is not None:
            return super().connect()
        started = time.monotonic()
        delays = (0.25, 0.75)
        for attempt in range(3):
            try:
                # connect() completes TCP/TLS setup before urllib3 sends HTTP.
                # Never catch these errors around request() or response reads.
                super().connect()
                return
            except (ssl.SSLEOFError, ConnectionResetError) as exc:
                self.close()
                exhausted = attempt == len(delays)
                logger.warning(
                    "HTTPS handshake {} host={} attempt={} elapsed_ms={:.0f} error_type={}",
                    "exhausted" if exhausted else "retry",
                    self.host,
                    attempt + 1,
                    (time.monotonic() - started) * 1000,
                    type(exc).__name__,
                )
                if exhausted:
                    raise
                time.sleep(delays[attempt] + random.uniform(0, 0.1))


class _HandshakePool(HTTPSConnectionPool):
    # urllib3's concrete HTTPSConnection does not satisfy its own protocol annotations.
    ConnectionCls: type[HTTPSConnection] = _HandshakeConnection  # pyright: ignore[reportIncompatibleVariableOverride]


class _HandshakeAdapter(HTTPAdapter):
    @override
    def init_poolmanager(self, connections: int, maxsize: int, block: bool = False, **pool_kwargs: Any) -> None:
        super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)
        # PoolManager initially references a shared dictionary. Copy it so
        # unrelated clients and proxy managers are never affected.
        self.poolmanager.pool_classes_by_scheme = {
            **self.poolmanager.pool_classes_by_scheme,
            "https": _HandshakePool,
        }


class _RequestSession(requests.Session):
    def __init__(self) -> None:
        super().__init__()
        self.mount("https://", _HandshakeAdapter(max_retries=0))


def request_session() -> requests.Session:
    """Create a session to close after one SDK request, including redirects.

    Only direct HTTPS EOF/reset failures during connection setup get up to
    three attempts. The caller's timeout applies to each connection attempt.
    HTTP responses and failures after transmission never trigger retries.
    """
    return _RequestSession()


def send_with_retries(
    endpoint: _RetryRequest, send: Callable[[float], requests.Response], *, max_retries: int, timeout: float
) -> requests.Response:
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
            raise requests.Timeout("SDK request retry deadline exceeded")
        try:
            response = send(remaining)
        except requests.RequestException as e:
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
