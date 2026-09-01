import base64
import json
import os
import sys
from typing import Any
from urllib.parse import urlparse

from notte_core.common.logging import logger

KEYRING_SERVICE = "notte-cli"
KEYRING_KEY = "api_key"

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
    if hostname is None:
        return "prod"
    return _HOST_TO_ENV_LABEL.get(hostname, hostname)


def _decode_cli_secret(secret: bytes) -> str | None:
    """Decode an item written by github.com/99designs/keyring."""
    try:
        item: dict[str, Any] = json.loads(secret)
        data = item.get("Data")
        if not isinstance(data, str):
            return None
        return base64.b64decode(data).decode()
    except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _get_from_secret_service(key: str) -> str | None:
    """Read the custom Secret Service collection used by notte-cli on Linux."""
    if sys.platform != "linux":
        return None

    try:
        import secretstorage

        bus = secretstorage.dbus_init()
        for collection in secretstorage.get_all_collections(bus):
            if collection.get_label() != KEYRING_SERVICE:
                continue
            for item in collection.search_items({"profile": key}):
                value = _decode_cli_secret(item.get_secret())
                if value:
                    return value
    except Exception as exc:
        # Keyring access is a best-effort fallback. Headless Linux environments
        # commonly have no Secret Service session available.
        logger.debug(f"Could not read notte-cli Secret Service keyring: {exc}")
    return None


def _get_from_system_keyring(key: str) -> str | None:
    """Read backends whose notte-cli representation matches Python keyring."""
    try:
        import keyring

        return keyring.get_password(KEYRING_SERVICE, key)
    except Exception as exc:
        logger.debug(f"Could not read notte-cli system keyring: {exc}")
        return None


def get_keyring_api_key(api_url: str) -> str | None:
    """Load the API key stored by notte-cli for the selected API environment."""
    env_key = f"{KEYRING_KEY}:{resolve_env_label(api_url)}"
    for key in (env_key, KEYRING_KEY if env_key == f"{KEYRING_KEY}:prod" else None):
        if key is None:
            continue
        value = _get_from_secret_service(key) or _get_from_system_keyring(key)
        if value:
            return value
    return None


def resolve_api_key(api_key: str | None, server_url: str) -> str | None:
    """Resolve an API key from code, environment, then the notte-cli keyring."""
    return api_key or os.getenv("NOTTE_API_KEY") or get_keyring_api_key(server_url)
