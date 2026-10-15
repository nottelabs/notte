import base64
import json
import subprocess
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from notte_core.logging import logger
from notte_sdk import NotteClient, auth
from notte_sdk.auth import _decode_cli_secret, get_keyring_api_key, resolve_api_key, resolve_env_label
from notte_sdk.errors import AuthenticationError

# Written by github.com/99designs/keyring v1.2.2 (file backend), as notte-cli does.
CLI_FILE_BACKEND_ITEMS = {
    "api_key:prod": (
        "eyJhbGciOiJQQkVTMi1IUzI1NitBMTI4S1ciLCJjcmVhdGVkIjoiMjAyNi0xMC0xMyAxNzo0Mzo1NS44NTYyNTQgKzAyMDAg"  # pragma: allowlist secret
        "Q0VTVCBtPSswLjAwMTIxMzMzNCIsImVuYyI6IkEyNTZHQ00iLCJwMmMiOjgxOTIsInAycyI6IjJlRnUzNmxvUC1hcWZycDIi"  # pragma: allowlist secret
        "fQ.ho4EAD9tJKYbAB4bsWSGN28F1ZwLW1HBaE8slpkroWuq1BjJPezMmg.LreqGyTAPL5vNr5t.s8C7TLUdH8QqBH0Rqclxm"  # pragma: allowlist secret
        "M8mWofXP-hRG95W8DsE6d7oBpkFFUk8WWNGgXpjgQLYsINPbDZdZo7gwi7trGsomjnoq61o2rMqKJo_-l04Otlo_FuhaNqlz"  # pragma: allowlist secret
        "clI9Qlx5Y4LVKayvFhFlp_mYgU-B7dr5jcbktm5VAXLUwwCbDCyI739SnDZ5tKMDqkPUJWwSZ2RRIM.RqXiRfzrZwmUxDwIH"  # pragma: allowlist secret
        "V-Ovw"  # pragma: allowlist secret
    ),
    "api_key:localhost": (
        "eyJhbGciOiJQQkVTMi1IUzI1NitBMTI4S1ciLCJjcmVhdGVkIjoiMjAyNi0xMC0xMyAxNzo0Mzo1NS44NTgwNjYgKzAyMDAg"  # pragma: allowlist secret
        "Q0VTVCBtPSswLjAwMzAyNTAwMSIsImVuYyI6IkEyNTZHQ00iLCJwMmMiOjgxOTIsInAycyI6IlFIdGFJR0wwbVpkekhHUnki"  # pragma: allowlist secret
        "fQ.b6-F_e6O_biMvmO46xuZfT8O-ItC8RQlQzvKogckPFYvxqTbx3ee4A.ZnLEpsJzzBOOXmMi.-MdGVGVKC5sQmEu3DwfgV"  # pragma: allowlist secret
        "weE4WbJ6tObBxCnOoEP6UQv-ObgC-9lDsAgbeeNtz-jTQed59Uq6aUf-BdY_FCE6Y0AHfmpbwL6lrVoEW6EeKfTcMYBd32uD"  # pragma: allowlist secret
        "rdcGbzDxSjWp_yZbR3GGQ9QEA8ob_Kt_hwcewpR3MnqjMHqzRnSrrJMuVOL3gbscPVNC6-lnvQq4A-abzd91x__8Bw.1YaAf"  # pragma: allowlist secret
        "hFRvb5kOm5RArIKfA"  # pragma: allowlist secret
    ),
    "api_key": (
        "eyJhbGciOiJQQkVTMi1IUzI1NitBMTI4S1ciLCJjcmVhdGVkIjoiMjAyNi0xMC0xMyAxNzo0Mzo1NS44NjExNTMgKzAyMDAg"  # pragma: allowlist secret
        "Q0VTVCBtPSswLjAwNjExMjc5MiIsImVuYyI6IkEyNTZHQ00iLCJwMmMiOjgxOTIsInAycyI6IkFhQms4eFpKTk13b1JIU3Mi"  # pragma: allowlist secret
        "fQ.WPsEhmuRTJy7OWIbyl257keA6Ua9d872fN2m5MzoaHPiX_Et3UXGEA.gp1vqaYqhHLu-4ek.ViVa9UYQWpsAo0XqNDQ9z"  # pragma: allowlist secret
        "JBFqq4qXJ69UozcCfYyjlzxnhF2stL0srDcGAaCGDB22Fq_9GYNrIPQuV9RBUQDfdsg9498UzzCNBh_8SF2cnRPy1l3zWWuM"  # pragma: allowlist secret
        "MjrwDAWk7p6W_APCemUAD7q5S4uICid_5fk4Z6NSCbJ2_AHhyGjrGWtMLl4T5vvSeX34MwzCZyyaQ.Bupml5_7riIx7rvax2"  # pragma: allowlist secret
        "ibyw"  # pragma: allowlist secret
    ),
}

CLI_FILE_BACKEND_VALUES = {
    "api_key:prod": "cli-prod-key",  # pragma: allowlist secret
    "api_key:localhost": "cli-local-key",  # pragma: allowlist secret
    "api_key": "cli-legacy-key",  # pragma: allowlist secret
}


def _file_value(key: str) -> str | None:
    item = auth._read_file_backend(key)
    return item[0] if item else None


def _write_cli_store(config_dir: Path, *keys: str) -> None:
    store = config_dir / ".notte" / "cli"
    store.mkdir(parents=True, exist_ok=True)
    for key in keys:
        (store / key).write_text(CLI_FILE_BACKEND_ITEMS[key])


@pytest.fixture
def cli_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An isolated notte-cli config dir, with no system credential store and no env overrides."""
    monkeypatch.setenv("NOTTE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("NOTTE_API_KEY", raising=False)
    monkeypatch.delenv("NOTTE_API_URL", raising=False)
    monkeypatch.setattr(auth, "_get_from_secret_service", lambda key: None)
    monkeypatch.setattr(auth, "_get_from_macos_keychain", lambda key: None)
    monkeypatch.setattr(auth, "_get_from_windows_credential_manager", lambda key: None)
    return tmp_path


def test_resolve_env_label_matches_cli() -> None:
    assert resolve_env_label("https://api.notte.cc") == "prod"
    assert resolve_env_label("https://us-prod.notte.cc") == "prod"
    assert resolve_env_label("https://us-staging.notte.cc") == "staging"
    assert resolve_env_label("https://us-dev-test.notte.cc") == "dev"
    assert resolve_env_label("http://localhost:8000") == "localhost"
    assert resolve_env_label("") == "prod"


def test_decode_cli_secret() -> None:
    encoded_key = base64.b64encode(b"test-key").decode()
    secret = json.dumps({"Key": "api_key:prod", "Data": encoded_key}).encode()

    assert _decode_cli_secret(secret) == "test-key"
    assert _decode_cli_secret(b"not-json") is None
    assert _decode_cli_secret(b"[]") is None
    assert _decode_cli_secret(json.dumps({"Data": "%%%"}).encode()) is None
    assert _decode_cli_secret(json.dumps({"Data": ""}).encode()) is None


@pytest.mark.parametrize("key", list(CLI_FILE_BACKEND_ITEMS))
def test_file_backend_reads_items_written_by_cli_library(cli_config_dir: Path, key: str) -> None:
    _write_cli_store(cli_config_dir, key)

    assert _file_value(key) == CLI_FILE_BACKEND_VALUES[key]


def test_file_backend_escapes_file_names_like_cli(cli_config_dir: Path) -> None:
    store = cli_config_dir / ".notte" / "cli"
    store.mkdir(parents=True)
    (store / "api_key:a%2Fb%25c").write_text(CLI_FILE_BACKEND_ITEMS["api_key:prod"])

    assert _file_value("api_key:a/b%c") == "cli-prod-key"


def test_file_backend_missing_or_invalid_entries(cli_config_dir: Path) -> None:
    store = cli_config_dir / ".notte" / "cli"
    assert _file_value("api_key:prod") is None

    store.mkdir(parents=True)
    (store / "api_key:prod").write_text("not a token")
    assert _file_value("api_key:prod") is None

    token = CLI_FILE_BACKEND_ITEMS["api_key:prod"]
    protected, rest = token.split(".", 1)
    tampered = protected + "." + rest[:-4] + ("AAAA" if not rest.endswith("AAAA") else "BBBB")
    (store / "api_key:prod").write_text(tampered)
    assert _file_value("api_key:prod") is None


def _jwe_with_header(header: dict[str, Any]) -> str:
    protected = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    return ".".join([protected, "AA", "AA", "AA", "AA"])


@pytest.mark.parametrize(
    "header",
    [
        {"alg": "dir", "enc": "A256GCM", "p2c": 8192, "p2s": "AA"},
        {"alg": "PBES2-HS256+A128KW", "enc": "A128GCM", "p2c": 8192, "p2s": "AA"},
        {"alg": "PBES2-HS256+A128KW", "enc": "A256GCM", "p2c": 10**9, "p2s": "AA"},
        {"alg": "PBES2-HS256+A128KW", "enc": "A256GCM", "p2c": 8192},
        {"alg": "PBES2-HS256+A128KW", "enc": "A256GCM", "p2c": 8192, "p2s": "AA", "zip": "DEF"},
    ],
)
def test_file_backend_rejects_unexpected_headers(header: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        _ = auth._decrypt_file_backend_token(_jwe_with_header(header), b"notte-cli-keyring")


def test_get_keyring_api_key_uses_environment_key(cli_config_dir: Path) -> None:
    _write_cli_store(cli_config_dir, "api_key:prod", "api_key:localhost")

    assert get_keyring_api_key("https://api.notte.cc") == "cli-prod-key"
    assert get_keyring_api_key("http://localhost:8000") == "cli-local-key"
    assert get_keyring_api_key("https://us-staging.notte.cc") is None


@pytest.mark.parametrize(
    "api_url", ["http://api.notte.cc", "http://us-staging.notte.cc", "http://example.com:8000", "ftp://api.notte.cc"]
)
def test_get_keyring_api_key_requires_https(cli_config_dir: Path, api_url: str) -> None:
    _write_cli_store(cli_config_dir, "api_key:prod", "api_key")

    assert get_keyring_api_key(api_url) is None


@pytest.mark.parametrize("api_url", ["http://localhost:8000", "http://127.0.0.1:8000", "http://[::1]:8000"])
def test_get_keyring_api_key_allows_plain_http_on_loopback(cli_config_dir: Path, api_url: str) -> None:
    store = cli_config_dir / ".notte" / "cli"
    store.mkdir(parents=True)
    label = resolve_env_label(api_url)
    (store / f"api_key:{label}").write_text(CLI_FILE_BACKEND_ITEMS["api_key:localhost"])

    assert get_keyring_api_key(api_url) == "cli-local-key"


def test_get_keyring_api_key_supports_legacy_prod_key(cli_config_dir: Path) -> None:
    _write_cli_store(cli_config_dir, "api_key")

    assert get_keyring_api_key("https://api.notte.cc") == "cli-legacy-key"
    # The legacy entry only ever held a production key.
    assert get_keyring_api_key("https://us-dev.notte.cc") is None


def _write_cli_item(config_dir: Path, key: str, value: str, description: str = "") -> None:
    """Write a file store entry encrypted the way 99designs/keyring does."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives.keywrap import aes_key_wrap

    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode().rstrip("=")

    salt = b"0123456789abcdef"
    header = {"alg": "PBES2-HS256+A128KW", "enc": "A256GCM", "p2c": 1000, "p2s": b64(salt)}
    protected = b64(json.dumps(header).encode())
    kek = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=16, salt=b"PBES2-HS256+A128KW\x00" + salt, iterations=1000
    ).derive(b"notte-cli-keyring")
    cek, iv = bytes(range(32)), bytes(12)
    item = {"Key": key, "Data": base64.b64encode(value.encode()).decode(), "Description": description}
    sealed = AESGCM(cek).encrypt(iv, json.dumps(item).encode(), protected.encode())
    store = config_dir / ".notte" / "cli"
    store.mkdir(parents=True, exist_ok=True)
    token = ".".join([protected, b64(aes_key_wrap(kek, cek)), b64(iv), b64(sealed[:-16]), b64(sealed[-16:])])
    _ = (store / key).write_text(token)


@pytest.mark.parametrize("platform", ["linux", "darwin", "win32"])
def test_get_keyring_api_key_store_precedence(
    cli_config_dir: Path, monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    system_reader = {
        "linux": "_get_from_secret_service",
        "darwin": "_get_from_macos_keychain",
        "win32": "_get_from_windows_credential_manager",
    }[platform]
    system: dict[str, str] = {}
    monkeypatch.setattr(auth, system_reader, system.get)

    # An entry written by an older CLI version is used when the system store has nothing...
    _write_cli_item(cli_config_dir, "api_key:prod", "old-version-key")
    assert get_keyring_api_key("https://api.notte.cc") == "old-version-key"
    # ...but may be older than the system store's entry, which wins.
    system["api_key:prod"] = "system-key"
    assert get_keyring_api_key("https://api.notte.cc") == "system-key"
    # An entry notte-cli marked current wins without reading the system store.
    _write_cli_item(cli_config_dir, "api_key:prod", "current-key", "notte-cli:current")
    monkeypatch.setattr(auth, system_reader, lambda key: pytest.fail("system store read"))
    assert get_keyring_api_key("https://api.notte.cc") == "current-key"


def test_resolve_api_key_precedence(cli_config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_cli_store(cli_config_dir, "api_key:prod")

    assert resolve_api_key("code-key", "https://api.notte.cc") == "code-key"
    monkeypatch.setenv("NOTTE_API_KEY", "env-key")
    with patch.object(auth, "get_keyring_api_key") as get_keyring:
        assert resolve_api_key(None, "https://api.notte.cc") == "env-key"
        get_keyring.assert_not_called()

    monkeypatch.delenv("NOTTE_API_KEY")
    assert resolve_api_key(None, "https://api.notte.cc") == "cli-prod-key"


class _FakeItem:
    def __init__(self, secret: bytes) -> None:
        self._secret = secret

    def get_secret(self) -> bytes:
        return self._secret


class _FakeCollection:
    def __init__(self, label: str, items: dict[str, bytes]) -> None:
        self._label = label
        self._items = items

    def get_label(self) -> str:
        return self._label

    def search_items(self, attributes: dict[str, str]) -> list[_FakeItem]:
        secret = self._items.get(attributes["profile"])
        return [] if secret is None else [_FakeItem(secret)]


class _FakeBus:
    closed = False

    def close(self) -> None:
        self.closed = True


def _cli_item(key: str, value: str) -> bytes:
    return json.dumps({"Key": key, "Data": base64.b64encode(value.encode()).decode()}).encode()


def test_secret_service_reads_cli_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = _FakeBus()
    collections = [
        _FakeCollection("Login", {"api_key:prod": _cli_item("api_key:prod", "other-app-key")}),
        _FakeCollection("notte-cli", {"api_key:prod": _cli_item("api_key:prod", "secret-service-key")}),
    ]
    fake = types.SimpleNamespace(dbus_init=lambda: bus, get_all_collections=lambda _bus: collections)
    monkeypatch.setitem(sys.modules, "secretstorage", fake)
    monkeypatch.setattr(sys, "platform", "linux")

    assert auth._get_from_secret_service("api_key:prod") == "secret-service-key"
    assert auth._get_from_secret_service("api_key:staging") is None
    assert bus.closed


def test_secret_service_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_bus() -> None:
        raise RuntimeError("no D-Bus session")

    monkeypatch.setitem(sys.modules, "secretstorage", types.SimpleNamespace(dbus_init=no_bus))
    monkeypatch.setattr(sys, "platform", "linux")
    assert auth._get_from_secret_service("api_key:prod") is None

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "secretstorage", None)
    assert auth._get_from_secret_service("api_key:prod") is None


def test_secret_service_calls_are_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    secretstorage = pytest.importorskip("secretstorage")
    timeouts: list[float | None] = []

    class UnresponsiveConnection:
        """A D-Bus connection whose Secret Service never answers."""

        def send_and_get_reply(self, message: Any, *, timeout: float | None = None) -> Any:
            timeouts.append(timeout)
            if timeout is None:
                raise AssertionError("D-Bus call made without a timeout")
            raise TimeoutError

        def close(self) -> None:
            pass

    monkeypatch.setattr(secretstorage, "dbus_init", UnresponsiveConnection)
    monkeypatch.setattr(sys, "platform", "linux")

    assert auth._get_from_secret_service("api_key:prod") is None
    assert timeouts == [auth._SECRET_SERVICE_TIMEOUT_SECONDS]


def test_keyring_failures_do_not_log_secrets(cli_config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = []
    sink = logger.add(lambda message: messages.append(str(message)), level="DEBUG")
    try:
        _write_cli_store(cli_config_dir, "api_key:prod")
        monkeypatch.setattr(auth, "_FILE_BACKEND_PASSWORD", b"wrong-password")
        assert get_keyring_api_key("https://api.notte.cc") is None
        monkeypatch.setattr(auth, "_FILE_BACKEND_PASSWORD", b"notte-cli-keyring")
        assert get_keyring_api_key("https://api.notte.cc") == "cli-prod-key"
    finally:
        logger.remove(sink)

    assert messages
    assert not any("cli-prod-key" in message for message in messages)


def test_client_uses_cli_keyring(cli_config_dir: Path) -> None:
    _write_cli_store(cli_config_dir, "api_key:prod")

    client = NotteClient()

    assert client.sessions.token == client.functions.token == client.files.token == "cli-prod-key"


def test_client_uses_cli_keyring_for_api_url(cli_config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_cli_store(cli_config_dir, "api_key:prod", "api_key:localhost")
    monkeypatch.setenv("NOTTE_API_URL", "http://localhost:8000")

    assert NotteClient().sessions.token == "cli-local-key"
    assert NotteClient(server_url="https://api.notte.cc").sessions.token == "cli-prod-key"


def test_client_env_key_overrides_cli_keyring(cli_config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_cli_store(cli_config_dir, "api_key:prod")
    monkeypatch.setenv("NOTTE_API_KEY", "env-key")

    assert NotteClient().sessions.token == "env-key"
    assert NotteClient(api_key="code-key").sessions.token == "code-key"  # pragma: allowlist secret


def test_client_reads_keyring_once(cli_config_dir: Path) -> None:
    _write_cli_store(cli_config_dir, "api_key:prod")

    with patch.object(auth, "get_keyring_api_key", wraps=auth.get_keyring_api_key) as get_keyring:
        client = NotteClient()

    assert get_keyring.call_count == 1
    assert client.personas.token == "cli-prod-key"


def test_client_without_any_key_raises_after_one_lookup(cli_config_dir: Path) -> None:
    with (
        patch.object(auth, "get_keyring_api_key", wraps=auth.get_keyring_api_key) as get_keyring,
        pytest.raises(AuthenticationError, match="notte auth login"),
    ):
        _ = NotteClient()

    assert get_keyring.call_count == 1


class _FakeSecurity:
    """Stands in for subprocess.run calls to the macOS `security` tool."""

    def __init__(self, items: dict[str, bytes], read_error: BaseException | None = None) -> None:
        self.items = items
        self.read_error = read_error
        self.calls: list[tuple[list[str], float | None]] = []

    def __call__(self, args: list[str], *, capture_output: bool, timeout: float | None, check: bool) -> Any:
        assert capture_output and not check
        self.calls.append((args, timeout))
        account = args[args.index("-a") + 1]
        if args[:4] != ["/usr/bin/security", "find-generic-password", "-s", "notte-cli"] or account not in self.items:
            return subprocess.CompletedProcess(args, 44, b"", b"The specified item could not be found in the keychain.")
        if "-w" not in args:
            return subprocess.CompletedProcess(args, 0, b'keychain: "login.keychain-db"', b"")
        if self.read_error is not None:
            raise self.read_error
        return subprocess.CompletedProcess(args, 0, self.items[account] + b"\n", b"")


def test_macos_keychain_reads_cli_item(monkeypatch: pytest.MonkeyPatch) -> None:
    security = _FakeSecurity({"api_key:prod": b"keychain-key"})
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(auth.subprocess, "run", security)

    assert auth._get_from_macos_keychain("api_key:prod") == "keychain-key"
    query = ["/usr/bin/security", "find-generic-password", "-s", "notte-cli", "-a", "api_key:prod"]
    assert security.calls == [
        (query, auth._KEYCHAIN_PROBE_TIMEOUT_SECONDS),
        ([*query, "-w"], auth._KEYCHAIN_READ_TIMEOUT_SECONDS),
    ]


def test_macos_keychain_skips_secret_read_when_item_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    security = _FakeSecurity({})
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(auth.subprocess, "run", security)

    assert auth._get_from_macos_keychain("api_key:prod") is None
    # Only the attribute lookup ran: asking for the secret could show a prompt.
    assert [args[-1] for args, _ in security.calls] == ["api_key:prod"]


@pytest.mark.parametrize(
    "error", [subprocess.TimeoutExpired("security", 30), FileNotFoundError("/usr/bin/security"), OSError("boom")]
)
def test_macos_keychain_failures_are_not_fatal(monkeypatch: pytest.MonkeyPatch, error: BaseException) -> None:
    messages: list[str] = []
    sink = logger.add(lambda message: messages.append(str(message)), level="DEBUG")
    try:
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(auth.subprocess, "run", _FakeSecurity({"api_key:prod": b"keychain-key"}, read_error=error))
        assert auth._get_from_macos_keychain("api_key:prod") is None
    finally:
        logger.remove(sink)
    assert not any("keychain-key" in message for message in messages)


def test_macos_keychain_denied_or_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")

    def denied(args: list[str], **_: Any) -> Any:
        code = 51 if "-w" in args else 0  # User canceled the access prompt.
        return subprocess.CompletedProcess(args, code, b"", b"")

    monkeypatch.setattr(auth.subprocess, "run", denied)
    assert auth._get_from_macos_keychain("api_key:prod") is None

    monkeypatch.setattr(auth.subprocess, "run", _FakeSecurity({"api_key:prod": b""}))
    assert auth._get_from_macos_keychain("api_key:prod") is None


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_macos_keychain_only_on_macos(monkeypatch: pytest.MonkeyPatch, platform: str) -> None:
    security = _FakeSecurity({"api_key:prod": b"keychain-key"})
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(auth.subprocess, "run", security)

    assert auth._get_from_macos_keychain("api_key:prod") is None
    assert security.calls == []


@pytest.mark.skipif(sys.platform == "win32", reason="checks the behavior without the Windows API")
def test_windows_credential_manager_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    assert auth._get_from_windows_credential_manager("api_key:prod") is None
    # Even when the platform claims to be Windows, a missing API means "no key".
    monkeypatch.setattr(sys, "platform", "win32")
    assert auth._get_from_windows_credential_manager("api_key:prod") is None


def test_get_keyring_api_key_reads_macos_keychain(cli_config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(auth, "_get_from_macos_keychain", lambda key: {"api_key:prod": "keychain-key"}.get(key))

    assert get_keyring_api_key("https://api.notte.cc") == "keychain-key"
    assert get_keyring_api_key("https://us-staging.notte.cc") is None
    # A saved key is never sent over plain HTTP, whichever store holds it.
    assert get_keyring_api_key("http://api.notte.cc") is None


def test_get_keyring_api_key_reads_windows_credential_manager(
    cli_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        auth,
        "_get_from_windows_credential_manager",
        lambda key: {"api_key": "wincred-legacy-key"}.get(key),  # pragma: allowlist secret
    )

    assert get_keyring_api_key("https://api.notte.cc") == "wincred-legacy-key"
    assert get_keyring_api_key("http://api.notte.cc") is None


def test_client_uses_macos_keychain(cli_config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(auth, "_get_from_macos_keychain", lambda key: {"api_key:prod": "keychain-key"}.get(key))

    assert NotteClient().sessions.token == "keychain-key"
