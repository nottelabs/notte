"""Request-scoped HTTPS recovery, before any application request is sent."""

import random
import ssl
import time
from typing import Any

import requests
from notte_core.common.logging import logger
from requests.adapters import HTTPAdapter
from typing_extensions import override
from urllib3.connection import HTTPSConnection
from urllib3.connectionpool import HTTPSConnectionPool


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
        super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)  # pyright: ignore[reportUnknownMemberType]
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
