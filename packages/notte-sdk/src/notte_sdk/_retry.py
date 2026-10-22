"""Automatic retries for transient API failures.

The Node SDK implements the same policy in ``node-sdk/src/retry.ts``.

What is retried:

- 503 and 529: the API declined the request before doing any work, so every
  method is retried.
- 502 and 504: a gateway lost or timed out on the upstream response, which may
  already have been processed. Only idempotent methods (GET, HEAD, OPTIONS,
  PUT, DELETE) are retried, so a POST such as starting a session or an agent is
  never sent twice.
- Connection failures that happen before the request is sent (connection
  refused, connect timeout): every method.
- Connection resets and read timeouts, which can happen after the request was
  sent: idempotent methods only.

Nothing else is retried: 500, other 5xx codes, and 4xx always surface as is.
"""

import random
import socket
import time
from collections.abc import Callable
from email.utils import parsedate_to_datetime

import anyio
import httpcore
import httpx

from notte_sdk.errors import (
    NotteConnectionError,
    NotteConnectTimeoutError,
    NotteRequestError,
    NotteRequestTimeoutError,
    NotteSSLError,
)

# Exceptions that wrap the socket or TLS error that caused them. anyio, the async
# transport's network layer, raises `BrokenResourceError` from the socket error.
_WRAPPERS = (
    NotteRequestError,
    httpx.HTTPError,
    httpcore.NetworkError,
    httpcore.TimeoutException,
    httpcore.ProtocolError,
    httpcore.ProxyError,
    anyio.BrokenResourceError,
)

DEFAULT_MAX_RETRIES = 3
"""Retries after the first attempt, unless ``NotteClient(max_retries=...)`` says otherwise."""
RETRY_BASE_DELAY_SECONDS = 1.0
"""Backoff before the first retry. Doubles with every retry, capped at ``RETRY_MAX_DELAY_SECONDS``."""
RETRY_MAX_DELAY_SECONDS = 10.0
RETRY_AFTER_MAX_SECONDS = 20.0
"""A longer ``Retry-After`` is not waited for: the error is returned instead."""

_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})
# Statuses that guarantee the API did no work.
_REFUSED_STATUSES = frozenset({503, 529})
# Gateway statuses: the upstream may already have processed the request.
_GATEWAY_STATUSES = frozenset({502, 504})


def is_idempotent_method(method: str) -> bool:
    return method.upper() in _IDEMPOTENT_METHODS


def is_retryable_status(status: int, method: str) -> bool:
    """Whether a response with this status is retried for this method."""
    return status in _REFUSED_STATUSES or (status in _GATEWAY_STATUSES and is_idempotent_method(method))


def root_cause(error: BaseException) -> BaseException:
    """The socket or TLS error below a transport failure, e.g. the `OSError` of an `httpx.ConnectError`.

    httpcore re-raises with `from None`, so the original error is only in `__context__`. An
    implicit `__context__` is never followed: it can be an unrelated error the caller was handling.
    """
    while isinstance(error, _WRAPPERS):
        inner = error.__cause__
        if inner is None and error.__suppress_context__:
            inner = error.__context__
        if inner is None:
            break
        error = inner
    return error


def _connection_never_opened(error: NotteConnectionError) -> bool:
    if isinstance(error, NotteConnectTimeoutError):
        return True
    if not isinstance(error.__cause__, httpx.ConnectError):
        return False
    # An unknown host is a configuration error, not a transient failure. A TLS
    # handshake reset was already retried by the transport.
    return not isinstance(root_cause(error), (socket.gaierror, ConnectionResetError))


def is_retryable_exception(error: BaseException, method: str) -> bool:
    """Whether a transport failure is a connection error that is retried for this method."""
    if isinstance(error, NotteSSLError):
        return False
    if isinstance(error, NotteConnectionError) and _connection_never_opened(error):
        return True
    if isinstance(error, (NotteConnectionError, NotteRequestTimeoutError)):
        return is_idempotent_method(method)
    return False


def parse_retry_after(header: str | None, now: float | None = None) -> float | None:
    """Parse a ``Retry-After`` header (seconds or an HTTP date) into seconds."""
    if not header:
        return None
    value = header.strip()
    try:
        seconds = float(value)
    except ValueError:
        pass
    else:
        return seconds if seconds >= 0 else None
    try:
        date = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if date.tzinfo is None:
        return None
    return max(0.0, date.timestamp() - (time.time() if now is None else now))


def backoff_delay(attempt: int, rand: Callable[[], float] = random.random) -> float:
    """Exponential backoff with full jitter for the retry following attempt ``attempt`` (0-based)."""
    return rand() * min(RETRY_MAX_DELAY_SECONDS, RETRY_BASE_DELAY_SECONDS * 2**attempt)


def retry_delay(attempt: int, retry_after: str | None, rand: Callable[[], float] = random.random) -> float | None:
    """Delay before retrying a response, or ``None`` when ``Retry-After`` exceeds the cap."""
    requested = parse_retry_after(retry_after)
    if requested is None:
        return backoff_delay(attempt, rand)
    return requested if requested <= RETRY_AFTER_MAX_SECONDS else None
