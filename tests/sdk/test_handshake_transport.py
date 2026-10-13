"""Real sockets distinguish a failed handshake from a lost POST response."""

import datetime
import ipaddress
import socket
import ssl
import struct
import threading
from contextlib import contextmanager
from unittest.mock import Mock, patch

import pytest
import requests
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from notte_sdk._transport import _HandshakeConnection, _HandshakePool, request_session
from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from pydantic import BaseModel
from urllib3.connection import HTTPSConnection
from urllib3.exceptions import ReadTimeoutError


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


@pytest.fixture(autouse=True)
def fast_backoff(monkeypatch):
    monkeypatch.setattr("notte_sdk._transport.time.sleep", Mock())
    monkeypatch.setattr("notte_sdk._transport.random.uniform", lambda *_: 0.05)


@pytest.mark.parametrize("method", ["GET", "POST", "PATCH", "DELETE"])
@pytest.mark.parametrize("reset", [False, True])
def test_handshake_recovery_sends_one_request(certificate, method, reset):
    with tls_server(certificate, failures=2, reset=reset) as (url, ca, state), request_session() as session:
        session.trust_env = False
        result = session.request(method, url, data=b"payload", verify=ca, timeout=2)
        assert result.status_code == 200
        assert state["connections"] == 3
        assert len(state["requests"]) == 1
        assert state["requests"][0][1] == b"payload"


@pytest.mark.parametrize("reset", [False, True])
def test_persistent_failure_is_bounded(certificate, reset):
    with tls_server(certificate, failures=10, reset=reset) as (url, ca, state), request_session() as session:
        session.trust_env = False
        with pytest.raises(requests.exceptions.ConnectionError):
            session.post(url, data=b"payload", verify=ca, timeout=2)
        assert state["connections"] == 3
        assert state["requests"] == []


@pytest.mark.parametrize("response", ["drop", "timeout", "503"])
def test_post_is_never_replayed_after_transmission(certificate, response):
    with tls_server(certificate, response=response) as (url, ca, state), request_session() as session:
        session.trust_env = False
        if response == "503":
            assert session.post(url, data=b"action", verify=ca, timeout=0.2).status_code == 503
        else:
            with pytest.raises(requests.exceptions.RequestException):
                session.post(url, data=b"action", verify=ca, timeout=0.2)
        assert state["connections"] == 1
        assert len(state["requests"]) == 1


def test_certificate_rejection_is_not_retried(certificate):
    with tls_server(certificate) as (url, _, state), request_session() as session:
        session.trust_env = False
        with pytest.raises(requests.exceptions.SSLError):
            session.get(url, timeout=2)
        assert state["connections"] == 1
        assert state["requests"] == []


def test_adapter_is_local_and_proxy_pool_is_unmodified():
    with request_session() as session, requests.Session() as normal:
        adapter = session.get_adapter("https://example.test")
        assert adapter.poolmanager.pool_classes_by_scheme["https"] is _HandshakePool
        assert (
            normal.get_adapter("https://example.test").poolmanager.pool_classes_by_scheme["https"] is not _HandshakePool
        )
        assert adapter.proxy_manager_for("http://proxy.test").pool_classes_by_scheme["https"] is not _HandshakePool
        assert type(session.get_adapter("http://example.test")) is requests.adapters.HTTPAdapter


@pytest.mark.parametrize(
    "error",
    [
        ssl.SSLError("unsupported protocol"),
        ssl.SSLCertVerificationError("bad cert"),
        ReadTimeoutError(None, "/", "timeout"),
    ],
)
def test_other_connection_errors_are_not_retried(error):
    conn = _HandshakeConnection("example.test")
    with patch.object(HTTPSConnection, "connect", side_effect=error) as connect:
        with pytest.raises(type(error)) as caught:
            conn.connect()
        assert caught.value is error
        assert connect.call_count == 1


def test_exhaustion_preserves_error_closes_sockets_and_logs_no_path():
    conn = _HandshakeConnection("example.test")
    error = ssl.SSLEOFError("sensitive exception text")
    with (
        patch.object(HTTPSConnection, "connect", side_effect=error) as connect,
        patch.object(conn, "close") as close,
        patch("notte_sdk._transport.logger.warning") as log,
    ):
        with pytest.raises(ssl.SSLEOFError) as caught:
            conn.connect()
        assert caught.value is error
        assert connect.call_count == close.call_count == 3
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


def test_explicit_redirect_retains_requests_behavior(certificate):
    with tls_server(certificate, failures=1, response="redirect") as (url, ca, state), request_session() as session:
        session.trust_env = False
        result = session.post(url, data=b"body", verify=ca, timeout=2)
        assert result.status_code == 200
        assert len(result.history) == 1
        assert state["connections"] == 3
        assert len(state["requests"]) == 2
        assert state["requests"][1][0].startswith(b"POST /next ")
        assert all(body == b"body" for _, body in state["requests"])


def test_backoff_and_per_attempt_timeout_are_preserved():
    conn = _HandshakeConnection("example.test", timeout=1.5)
    timeouts = []

    def fail():
        timeouts.append(conn.timeout)
        raise ConnectionResetError("reset")

    with patch.object(HTTPSConnection, "connect", side_effect=fail), patch("notte_sdk._transport.time.sleep") as sleep:
        with pytest.raises(ConnectionResetError):
            conn.connect()
        assert timeouts == [1.5, 1.5, 1.5]
        assert [args.args[0] for args in sleep.call_args_list] == [0.3, 0.8]
