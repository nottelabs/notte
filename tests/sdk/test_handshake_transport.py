"""Real sockets distinguish a failed handshake from a lost POST response."""

import datetime
import ipaddress
import socket
import ssl
import struct
import threading
from contextlib import contextmanager
from unittest.mock import Mock, patch

import httpcore
import httpx
import pytest
import requests
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from notte_sdk._transport import _HandshakeBackend, _HandshakeStream, http_client, send
from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from notte_sdk.errors import NotteConnectionError, NotteRequestError, NotteSSLError
from pydantic import BaseModel


@pytest.fixture
def certificate(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), False)
        .sign(key, hashes.SHA256())
    )
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    return context, str(cert_path)


@contextmanager
def tls_server(certificate, *, failures=0, reset=False, response="ok"):
    context, cert_path = certificate
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(0.1)
    stopped = threading.Event()
    state = {"connections": 0, "requests": [], "errors": []}

    def serve():
        while not stopped.is_set():
            try:
                conn, _ = listener.accept()
            except socket.timeout:
                continue
            try:
                conn.settimeout(2)
                state["connections"] += 1
                if state["connections"] <= failures:
                    # Consume ClientHello so a clean close produces TLS EOF.
                    conn.recv(8192)
                    if reset:
                        conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
                    conn.close()
                    continue
                with context.wrap_socket(conn, server_side=True) as tls:
                    data = b""
                    while b"\r\n\r\n" not in data:
                        chunk = tls.recv(8192)
                        if not chunk:
                            raise EOFError("client closed before headers")
                        data += chunk
                    head, body = data.split(b"\r\n\r\n", 1)
                    length = next(
                        (
                            int(line.split(b":", 1)[1])
                            for line in head.split(b"\r\n")
                            if line.lower().startswith(b"content-length:")
                        ),
                        0,
                    )
                    while len(body) < length:
                        chunk = tls.recv(8192)
                        if not chunk:
                            raise EOFError("client closed before body")
                        body += chunk
                    state["requests"].append((head, body))
                    if response == "redirect" and len(state["requests"]) == 1:
                        tls.sendall(
                            b"HTTP/1.1 307 Temporary Redirect\r\nLocation: /next\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                        )
                        continue
                    if response == "drop":
                        continue
                    if response == "timeout":
                        stopped.wait(0.5)
                        continue
                    status = b"503 Service Unavailable" if response == "503" else b"200 OK"
                    tls.sendall(b"HTTP/1.1 " + status + b"\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}")
            except ssl.SSLError:
                # Expected when the client rejects the test certificate.
                conn.close()
            except Exception as exc:
                state["errors"].append(exc)
                conn.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield f"https://127.0.0.1:{listener.getsockname()[1]}", cert_path, state
    finally:
        stopped.set()
        thread.join(3)
        listener.close()
        assert not thread.is_alive()
        assert not state["errors"]


PROXY_VARIABLES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")


@pytest.fixture(autouse=True)
def fast_backoff(monkeypatch):
    monkeypatch.setattr("notte_sdk._transport.time.sleep", Mock())
    monkeypatch.setattr("notte_sdk._transport.random.uniform", lambda *_: 0.05)
    # Connect directly to the local test server.
    for name in PROXY_VARIABLES:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def trusted(monkeypatch):
    """Create SDK clients that trust a CA bundle, configured as requests users configure it."""

    def client(ca: str) -> httpx.Client:
        monkeypatch.setenv("REQUESTS_CA_BUNDLE", ca)
        return http_client()

    return client


@pytest.mark.parametrize("method", ["GET", "POST", "PATCH", "DELETE"])
@pytest.mark.parametrize("reset", [False, True])
def test_handshake_recovery_sends_one_request(certificate, trusted, method, reset):
    with tls_server(certificate, failures=2, reset=reset) as (url, ca, state), trusted(ca) as client:
        result = send(client, client.build_request(method, url, content=b"payload", timeout=2))
        assert result.status_code == 200
        assert state["connections"] == 3
        assert len(state["requests"]) == 1
        assert state["requests"][0][1] == b"payload"


@pytest.mark.parametrize("reset", [False, True])
def test_persistent_failure_is_bounded(certificate, trusted, reset):
    with tls_server(certificate, failures=10, reset=reset) as (url, ca, state), trusted(ca) as client:
        with pytest.raises(requests.exceptions.ConnectionError) as error:
            send(client, client.build_request("POST", url, content=b"payload", timeout=2))
        assert isinstance(error.value, NotteSSLError if not reset else NotteConnectionError)
        assert state["connections"] == 3
        assert state["requests"] == []


@pytest.mark.parametrize("response", ["drop", "timeout", "503"])
def test_post_is_never_replayed_after_transmission(certificate, trusted, response):
    with tls_server(certificate, response=response) as (url, ca, state), trusted(ca) as client:
        request = client.build_request("POST", url, content=b"action", timeout=0.2)
        if response == "503":
            assert send(client, request).status_code == 503
        else:
            with pytest.raises(requests.exceptions.RequestException) as error:
                send(client, request)
            assert isinstance(error.value, NotteRequestError)
        assert state["connections"] == 1
        assert len(state["requests"]) == 1


def test_certificate_rejection_is_not_retried(certificate, monkeypatch):
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.delenv("CURL_CA_BUNDLE", raising=False)
    with tls_server(certificate) as (url, _, state), http_client() as client:
        with pytest.raises(requests.exceptions.SSLError) as error:
            send(client, client.build_request("GET", url, timeout=2))
        assert isinstance(error.value, NotteSSLError)
        assert state["connections"] == 1
        assert state["requests"] == []


def test_handshake_backend_is_local_and_proxy_pool_is_unmodified(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.test:3128")
    with http_client() as client, httpx.Client() as normal:
        assert isinstance(client._transport._pool._network_backend, _HandshakeBackend)
        assert not isinstance(normal._transport._pool._network_backend, _HandshakeBackend)
        proxy = client._transport_for_url(httpx.URL("https://example.test"))
        assert proxy is not client._transport
        assert isinstance(proxy._pool, httpcore.HTTPProxy)
        assert not isinstance(proxy._pool._network_backend, _HandshakeBackend)


class FakeStream(httpcore.NetworkStream):
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.closed = False
        self.handshakes: list[float | None] = []

    def read(self, max_bytes, timeout=None):
        return b""

    def write(self, buffer, timeout=None):
        pass

    def close(self):
        self.closed = True

    def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        self.handshakes.append(timeout)
        if self.error is not None:
            raise self.error
        return self


def handshake_failure(cause: BaseException) -> httpcore.ConnectError:
    # httpcore raises ConnectError from the socket error, as SyncStream.start_tls does.
    error = httpcore.ConnectError(str(cause))
    error.__cause__ = cause
    return error


@pytest.mark.parametrize(
    "cause",
    [
        ssl.SSLError("unsupported protocol"),
        ssl.SSLCertVerificationError("bad cert"),
        ConnectionRefusedError("refused"),
    ],
)
def test_other_connection_errors_are_not_retried(cause):
    error = handshake_failure(cause)
    connect = Mock(return_value=FakeStream(error))
    stream = _HandshakeStream(connect, "example.test")
    with pytest.raises(httpcore.ConnectError) as caught:
        stream.start_tls(ssl.create_default_context(), "example.test", 1.0)
    assert caught.value is error
    assert connect.call_count == 1


def test_handshake_timeouts_are_not_retried():
    error = httpcore.ConnectTimeout("handshake timed out")
    connect = Mock(return_value=FakeStream(error))
    stream = _HandshakeStream(connect, "example.test")
    with pytest.raises(httpcore.ConnectTimeout) as caught:
        stream.start_tls(ssl.create_default_context(), "example.test", 1.0)
    assert caught.value is error
    assert connect.call_count == 1


def test_exhaustion_preserves_error_closes_sockets_and_logs_no_path():
    error = handshake_failure(ssl.SSLEOFError("sensitive exception text"))
    streams = [FakeStream(error) for _ in range(3)]
    connect = Mock(side_effect=streams)
    with patch("notte_sdk._transport.logger.warning") as log:
        stream = _HandshakeStream(connect, "example.test")
        with pytest.raises(httpcore.ConnectError) as caught:
            stream.start_tls(ssl.create_default_context(), "example.test", 1.0)
        assert caught.value is error
        assert connect.call_count == 3
        assert all(item.closed for item in streams)
        assert log.call_count == 3
        assert "sensitive" not in str(log.call_args_list)


class Payload(BaseModel):
    value: str


@pytest.mark.parametrize("multipart", [False, True])
def test_sdk_preserves_headers_query_and_body_during_recovery(certificate, monkeypatch, tmp_path, multipart):
    monkeypatch.setattr(BaseClient, "check_and_warn_version_mismatch", lambda _: None)
    monkeypatch.setenv("NOTTE_DB_PREVIEW_BRANCH", "preview-test")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    with tls_server(certificate, failures=1) as (url, ca, state):
        monkeypatch.setenv("REQUESTS_CA_BUNDLE", ca)
        client = BaseClient(None, None, server_url=url, api_key="test-token")
        endpoint = NotteEndpoint(
            path="action", method="POST", request=Payload(value="test"), params=Payload(value="query"), response=Payload
        )
        if multipart:
            file = tmp_path / "upload.txt"
            file.write_text("upload-data")
            endpoint = endpoint.with_file(str(file))
        try:
            assert client._request(endpoint, timeout=2) == {}
        finally:
            if multipart:
                endpoint.files["file"].close()
        assert state["connections"] == 2
        assert len(state["requests"]) == 1
        head, body = state["requests"][0]
        assert b"POST /action?value=query HTTP/1.1" in head
        assert b"Authorization: Bearer test-token" in head
        assert b"x-db-preview: preview-test" in head
        if multipart:
            assert b"multipart/form-data" in head
            assert b"upload-data" in body
            assert b'name="value"' in body
        else:
            assert b"application/json" in head
            assert body == b'{"value":"test"}'


def test_explicit_redirect_retains_requests_behavior(certificate, trusted):
    with tls_server(certificate, failures=1, response="redirect") as (url, ca, state), trusted(ca) as client:
        result = send(client, client.build_request("POST", url, content=b"body", timeout=2))
        assert result.status_code == 200
        assert len(result.history) == 1
        assert state["connections"] == 3
        assert len(state["requests"]) == 2
        assert state["requests"][1][0].startswith(b"POST /next ")
        assert all(body == b"body" for _, body in state["requests"])


def test_backoff_and_per_attempt_timeout_are_preserved():
    error = handshake_failure(ConnectionResetError("reset"))
    streams = [FakeStream(error) for _ in range(3)]
    timeouts = []

    def connect(host, port, timeout=None, local_address=None, socket_options=None):
        timeouts.append(timeout)
        return streams[len(timeouts) - 1]

    with (
        patch.object(httpcore.SyncBackend, "connect_tcp", side_effect=connect),
        patch("notte_sdk._transport.time.sleep") as sleep,
    ):
        stream = _HandshakeBackend().connect_tcp("example.test", 443, timeout=1.5)
        with pytest.raises(httpcore.ConnectError):
            stream.start_tls(ssl.create_default_context(), "example.test", 1.5)
        assert timeouts == [1.5, 1.5, 1.5]
        assert [item.handshakes for item in streams] == [[1.5], [1.5], [1.5]]
        assert [args.args[0] for args in sleep.call_args_list] == [0.3, 0.8]
