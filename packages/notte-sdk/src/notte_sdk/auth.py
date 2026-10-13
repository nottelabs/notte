"""Read the API key saved by `notte auth login`.

notte-cli stores its key with github.com/99designs/keyring, which picks the
first available backend among Secret Service, KWallet, pass and an encrypted
file under the CLI config directory. This module reads the Secret Service and
file backends, which cover Linux desktops, macOS, Windows and headless hosts.
Every lookup is best effort: any failure means "no key found".
"""

import base64
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from notte_core.common.logging import logger

KEYRING_SERVICE = "notte-cli"
KEYRING_KEY = "api_key"
MISSING_API_KEY_MESSAGE = "No API key found. Provide api_key, set NOTTE_API_KEY, or run 'notte auth login'."

# Fixed password notte-cli uses for its encrypted file backend.
_FILE_BACKEND_PASSWORD = b"notte-cli-keyring"  # pragma: allowlist secret
_CONFIG_DIR_ENV = "NOTTE_CONFIG_DIR"
_CONFIG_DIR_NAME = Path(".notte") / "cli"
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


def _decode_cli_secret(secret: bytes) -> str | None:
    """Decode a keyring item serialized by github.com/99designs/keyring."""
    try:
        item: Any = json.loads(secret)
        if not isinstance(item, dict):
            return None
        data = cast(dict[str, Any], item).get("Data")
        if not isinstance(data, str):
            return None
        return base64.b64decode(data, validate=True).decode() or None
    except (UnicodeDecodeError, ValueError, TypeError):
        return None


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


def _get_from_file_backend(key: str) -> str | None:
    """Read the encrypted file notte-cli writes when no system keyring is available."""
    try:
        # 99designs/keyring percent-encodes '%' and '/' in file names.
        filename = key.replace("%", "%25").replace("/", "%2F")
        path = _cli_config_dir() / filename
        if not path.is_file():
            return None
        return _decode_cli_secret(_decrypt_file_backend_token(path.read_text(), _FILE_BACKEND_PASSWORD))
    except Exception as exc:
        logger.debug(f"Could not read notte-cli file keyring: {type(exc).__name__}")
        return None


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
            for collection in secretstorage.get_all_collections(bus):
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
        value = _get_from_secret_service(key) or _get_from_file_backend(key)
        if value:
            return value
    return None


def resolve_api_key(api_key: str | None, server_url: str) -> str | None:
    """Resolve an API key from code, then `NOTTE_API_KEY`, then the notte-cli keyring."""
    return api_key or os.getenv("NOTTE_API_KEY") or get_keyring_api_key(server_url)
