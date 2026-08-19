import base64
import json
import os
from unittest.mock import patch

from notte_sdk import NotteClient
from notte_sdk.auth import _decode_cli_secret, get_keyring_api_key, resolve_api_key, resolve_env_label


def test_resolve_env_label_matches_cli() -> None:
    assert resolve_env_label("https://api.notte.cc") == "prod"
    assert resolve_env_label("https://us-staging.notte.cc") == "staging"
    assert resolve_env_label("http://localhost:8000") == "localhost"
    assert resolve_env_label("") == "prod"


def test_decode_cli_secret() -> None:
    encoded_key = base64.b64encode(b"test-key").decode()
    secret = json.dumps({"Key": "api_key:prod", "Data": encoded_key}).encode()

    assert _decode_cli_secret(secret) == "test-key"
    assert _decode_cli_secret(b"not-json") is None


def test_get_keyring_api_key_uses_environment_key() -> None:
    with (
        patch("notte_sdk.auth._get_from_secret_service", side_effect=lambda key: f"value-for-{key}"),
        patch("notte_sdk.auth._get_from_system_keyring", return_value=None),
    ):
        assert get_keyring_api_key("https://us-dev.notte.cc") == "value-for-api_key:dev"


def test_get_keyring_api_key_supports_legacy_prod_key() -> None:
    values = {"api_key": "legacy-key"}  # pragma: allowlist secret
    with (
        patch("notte_sdk.auth._get_from_secret_service", side_effect=lambda key: values.get(key)),
        patch("notte_sdk.auth._get_from_system_keyring", return_value=None),
    ):
        assert get_keyring_api_key("https://api.notte.cc") == "legacy-key"


def test_resolve_api_key_precedence(monkeypatch) -> None:
    monkeypatch.setenv("NOTTE_API_KEY", "env-key")
    with patch("notte_sdk.auth.get_keyring_api_key", return_value="keyring-key") as get_keyring:
        assert resolve_api_key("code-key", "https://api.notte.cc") == "code-key"
        assert resolve_api_key(None, "https://api.notte.cc") == "env-key"
        get_keyring.assert_not_called()

    monkeypatch.delenv("NOTTE_API_KEY")
    with patch("notte_sdk.auth.get_keyring_api_key", return_value="keyring-key"):
        assert resolve_api_key(None, "https://api.notte.cc") == "keyring-key"


def test_client_only_reads_keyring_once() -> None:
    with (
        patch.dict(os.environ, {}, clear=True),
        patch("notte_sdk.endpoints.base.resolve_api_key", return_value="keyring-key") as resolve,
    ):
        client = NotteClient()

    assert resolve.call_count == 1
    assert client.sessions.token == client.workflows.token == "keyring-key"
