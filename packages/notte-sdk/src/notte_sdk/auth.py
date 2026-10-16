"""Read the API key saved by `notte auth login`.

notte-cli stores its key with github.com/99designs/keyring: in the macOS
Keychain, the Windows Credential Manager, a Linux Secret Service, or an
encrypted file under the CLI config directory when no system store is
available. This module reads all four. KWallet and pass are not read.
Every lookup is best effort: any failure means "no key found".
"""

import base64
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast, final
from urllib.parse import urlparse

from notte_core.logging import logger

KEYRING_SERVICE = "notte-cli"
KEYRING_KEY = "api_key"
MISSING_API_KEY_MESSAGE = "No API key found. Provide api_key, set NOTTE_API_KEY, or run 'notte auth login'."

# Fixed password notte-cli uses for its encrypted file backend.
_FILE_BACKEND_PASSWORD = b"notte-cli-keyring"  # pragma: allowlist secret
_CONFIG_DIR_ENV = "NOTTE_CONFIG_DIR"
_CONFIG_DIR_NAME = Path(".notte") / "cli"
# A Secret Service that accepts a call but never replies must not hang the client.
_SECRET_SERVICE_TIMEOUT_SECONDS = 2.0
# Checking that a Keychain item exists never prompts, so it gets a short bound.
_KEYCHAIN_PROBE_TIMEOUT_SECONDS = 5.0
# Reading the secret can show a Keychain access prompt, which needs time to answer.
_KEYCHAIN_READ_TIMEOUT_SECONDS = 30.0
_SECURITY_TOOL = "/usr/bin/security"
# Prefix 99designs/keyring adds to Windows Credential Manager target names.
_WINCRED_PREFIX = "keyring"
# notte-cli marks file entries it knows are current (see _get_from_cli_stores).
_FILE_CURRENT_MARKER = "notte-cli:current"
# Upper bound on PBKDF2 iterations accepted from a file header.
_MAX_PBES2_ITERATIONS = 10_000_000

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}

_HOST_TO_ENV_LABEL = {
    "api.notte.cc": "prod",
    "us-prod.notte.cc": "prod",
    "us-staging.notte.cc": "staging",
    "us-dev.notte.cc": "dev",
    "us-dev-test.notte.cc": "dev",
}


def resolve_env_label(api_url: str) -> str:
    """Return the notte-cli keyring environment label for an API URL."""
    hostname = urlparse(api_url).hostname
    if not hostname:
        return "prod"
    return _HOST_TO_ENV_LABEL.get(hostname, hostname)


def _decode_cli_item(secret: bytes) -> tuple[str, bool] | None:
    """Decode a keyring item serialized by github.com/99designs/keyring.

    Returns the value and whether notte-cli marked the entry as current.
    """
    try:
        item: Any = json.loads(secret)
        if not isinstance(item, dict):
            return None
        fields = cast(dict[str, Any], item)
        data = fields.get("Data")
        if not isinstance(data, str):
            return None
        value = base64.b64decode(data, validate=True).decode()
        return (value, fields.get("Description") == _FILE_CURRENT_MARKER) if value else None
    except (UnicodeDecodeError, ValueError, TypeError):
        return None


def _decode_cli_secret(secret: bytes) -> str | None:
    """Decode the value of a keyring item serialized by github.com/99designs/keyring."""
    item = _decode_cli_item(secret)
    return item[0] if item else None


def _b64url_decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def _decrypt_file_backend_token(token: str, password: bytes) -> bytes:
    """Decrypt a PBES2-HS256+A128KW / A256GCM compact JWE token."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives.keywrap import aes_key_unwrap

    parts = token.strip().split(".")
    if len(parts) != 5:
        raise ValueError("not a compact JWE token")
    protected, encrypted_key, iv, ciphertext, tag = parts
    decoded_header: Any = json.loads(_b64url_decode(protected))
    if not isinstance(decoded_header, dict):
        raise ValueError("invalid JWE header")
    header = cast(dict[str, Any], decoded_header)
    alg = header.get("alg")
    iterations = header.get("p2c")
    salt_input = header.get("p2s")
    if alg != "PBES2-HS256+A128KW" or header.get("enc") != "A256GCM" or "zip" in header:
        raise ValueError("unsupported JWE algorithm")
    if not isinstance(iterations, int) or not 0 < iterations <= _MAX_PBES2_ITERATIONS:
        raise ValueError("invalid PBES2 iteration count")
    if not isinstance(salt_input, str):
        raise ValueError("missing PBES2 salt")

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=16,
        salt=alg.encode() + b"\x00" + _b64url_decode(salt_input),
        iterations=iterations,
    )
    cek = aes_key_unwrap(kdf.derive(password), _b64url_decode(encrypted_key))
    return AESGCM(cek).decrypt(
        _b64url_decode(iv),
        _b64url_decode(ciphertext) + _b64url_decode(tag),
        protected.encode("ascii"),
    )


def _cli_config_dir() -> Path:
    base = os.getenv(_CONFIG_DIR_ENV)
    return (Path(base) if base else Path.home()) / _CONFIG_DIR_NAME


def _read_file_backend(key: str) -> tuple[str, bool] | None:
    """Read the encrypted file notte-cli writes when no system keyring is available.

    Returns the value and whether notte-cli marked the entry as current.
    """
    try:
        # 99designs/keyring percent-encodes '%' and '/' in file names.
        filename = key.replace("%", "%25").replace("/", "%2F")
        path = _cli_config_dir() / filename
        if not path.is_file():
            return None
        return _decode_cli_item(_decrypt_file_backend_token(path.read_text(), _FILE_BACKEND_PASSWORD))
    except Exception as exc:
        logger.debug(f"Could not read notte-cli file keyring: {type(exc).__name__}")
        return None


class _BoundedDBusConnection:
    """Wrap a jeepney connection so every D-Bus call waits a bounded time for its reply."""

    def __init__(self, connection: Any) -> None:
        self._connection: Any = connection

    def send_and_get_reply(self, message: Any, *, timeout: float | None = None) -> Any:
        return self._connection.send_and_get_reply(
            message, timeout=_SECRET_SERVICE_TIMEOUT_SECONDS if timeout is None else timeout
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


def _get_from_secret_service(key: str) -> str | None:
    """Read the Secret Service collection notte-cli uses on Linux."""
    if not sys.platform.startswith("linux"):
        return None

    try:
        # Imported dynamically: secretstorage is only installed on Linux.
        secretstorage: Any = importlib.import_module("secretstorage")
        bus: Any = secretstorage.dbus_init()
        try:
            collection: Any
            for collection in secretstorage.get_all_collections(_BoundedDBusConnection(bus)):
                if collection.get_label() != KEYRING_SERVICE:
                    continue
                item: Any
                for item in collection.search_items({"profile": key}):
                    value = _decode_cli_secret(item.get_secret())
                    if value:
                        return value
        finally:
            bus.close()
    except Exception as exc:
        # Headless Linux hosts and containers usually have no Secret Service.
        logger.debug(f"Could not read notte-cli Secret Service keyring: {type(exc).__name__}")
    return None


def _platform() -> str:
    """Return `sys.platform` as a plain string, so type checkers check every platform branch on any OS."""
    return sys.platform


def _get_from_macos_keychain(key: str) -> str | None:
    """Read the generic password notte-cli stores in the macOS Keychain.

    Items are stored with service `notte-cli`, the key as account, and the raw
    API key as data. Only the CLI is trusted to read them without asking, so
    the read can show an access prompt; it is bounded and skipped when no item
    exists.
    """
    if _platform() != "darwin":
        return None

    query = [_SECURITY_TOOL, "find-generic-password", "-s", KEYRING_SERVICE, "-a", key]
    try:
        # Looking up attributes never prompts: only ask for the secret when the item exists.
        probe = subprocess.run(query, capture_output=True, timeout=_KEYCHAIN_PROBE_TIMEOUT_SECONDS, check=False)
        if probe.returncode != 0:
            return None
        result = subprocess.run(
            [*query, "-w"], capture_output=True, timeout=_KEYCHAIN_READ_TIMEOUT_SECONDS, check=False
        )
        if result.returncode != 0:
            return None
        value = result.stdout.decode()
        return value.removesuffix("\n") or None
    except Exception as exc:
        logger.debug(f"Could not read notte-cli Keychain item: {type(exc).__name__}")
        return None


def _get_from_windows_credential_manager(key: str) -> str | None:
    """Read the generic credential notte-cli stores in the Windows Credential Manager.

    99designs/keyring names it `keyring:notte-cli:<key>` and stores the raw API key as its blob.
    """
    if _platform() != "win32":
        return None

    try:
        import ctypes
        from ctypes import wintypes

        @final
        class _Credential(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
                ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        cred_type_generic = 1
        # WinDLL only exists on Windows: look it up dynamically so type checking passes on every OS.
        win_dll: Any = vars(ctypes)["WinDLL"]
        advapi32: Any = win_dll("advapi32")
        cred_read: Any = advapi32.CredReadW
        cred_read.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(_Credential)),
        ]
        cred_read.restype = wintypes.BOOL
        cred_free: Any = advapi32.CredFree
        cred_free.argtypes = [ctypes.c_void_p]
        cred_free.restype = None

        credential = ctypes.POINTER(_Credential)()
        target = f"{_WINCRED_PREFIX}:{KEYRING_SERVICE}:{key}"
        if not cred_read(target, cred_type_generic, 0, ctypes.byref(credential)):
            return None
        try:
            blob = ctypes.string_at(credential.contents.CredentialBlob, credential.contents.CredentialBlobSize)
        finally:
            cred_free(credential)
        return blob.decode() or None
    except Exception as exc:
        logger.debug(f"Could not read notte-cli Credential Manager entry: {type(exc).__name__}")
        return None


def _get_from_system_store(key: str) -> str | None:
    platform = _platform()
    if platform == "darwin":
        return _get_from_macos_keychain(key)
    if platform == "win32":
        return _get_from_windows_credential_manager(key)
    return _get_from_secret_service(key)


def _get_from_cli_stores(key: str) -> str | None:
    """Read `key` the way notte-cli does.

    notte-cli marks the file entries it knows are current: a key saved while
    no system store was usable, or the identical copy it keeps after moving a
    key into the system store. A marked entry wins, which also avoids a
    Keychain access prompt. Otherwise the system store wins, and an unmarked
    entry, written by an older CLI version, is only used when the system
    store has nothing.
    """
    file_item = _read_file_backend(key)
    if file_item is not None and file_item[1]:
        return file_item[0]
    return _get_from_system_store(key) or (file_item[0] if file_item else None)


def _is_secure_api_url(api_url: str) -> bool:
    """Only send saved keys over HTTPS, or to a server on this machine."""
    parsed = urlparse(api_url)
    return parsed.scheme == "https" or parsed.hostname in _LOOPBACK_HOSTS


def get_keyring_api_key(api_url: str) -> str | None:
    """Load the API key stored by notte-cli for the API environment of `api_url`."""
    if not _is_secure_api_url(api_url):
        logger.debug("Not using the notte-cli keyring for a non-HTTPS API URL")
        return None
    env_label = resolve_env_label(api_url)
    keys = [f"{KEYRING_KEY}:{env_label}"]
    if env_label == "prod":
        # Entry written by notte-cli versions that predate per-environment keys.
        keys.append(KEYRING_KEY)
    for key in keys:
        value = _get_from_cli_stores(key)
        if value:
            return value
    return None


def resolve_api_key(api_key: str | None, server_url: str) -> str | None:
    """Resolve an API key from code, then `NOTTE_API_KEY`, then the notte-cli keyring."""
    return api_key or os.getenv("NOTTE_API_KEY") or get_keyring_api_key(server_url)
