"""Integration tests for BitwardenVault — validates the bws CLI binary is installed and responds correctly.

Tests that require a real BWS_ACCESS_TOKEN are skipped unless the env var is set.
Basic CLI validation tests run whenever the `bws` binary is available.
"""

import asyncio
import os
import shutil

import pytest
from notte_core.credentials.bitwarden import BitwardenVault

BWS_AVAILABLE = shutil.which("bws") is not None
BWS_TOKEN = os.environ.get("BWS_ACCESS_TOKEN", "")
BWS_AUTHENTICATED = BWS_AVAILABLE and bool(BWS_TOKEN)

pytestmark = pytest.mark.skipif(not BWS_AVAILABLE, reason="bws CLI not installed")


def test_bws_vault_validates_missing_token() -> None:
    vault = BitwardenVault(access_token="")
    with pytest.raises(ValueError, match="access token required"):
        vault.start()


def test_bws_vault_start_fails_with_invalid_token() -> None:
    vault = BitwardenVault(access_token="invalid-token")
    with pytest.raises(RuntimeError, match="bws command failed"):
        vault.start()


@pytest.mark.skipif(not BWS_AUTHENTICATED, reason="BWS_ACCESS_TOKEN not set")
def test_list_secrets() -> None:
    with BitwardenVault() as vault:
        creds = asyncio.run(vault.list_credentials_async())
        assert isinstance(creds, list)


@pytest.mark.skipif(not BWS_AUTHENTICATED, reason="BWS_ACCESS_TOKEN not set")
def test_get_credentials_for_known_domain() -> None:
    """Requires at least one secret in the BWS project with a known URL."""
    with BitwardenVault() as vault:
        creds = asyncio.run(vault.list_credentials_async())
        if len(creds) == 0:
            pytest.skip("No secrets found in BWS project")
        first_url = creds[0].url
        result = asyncio.run(vault.get_credentials_async(first_url))
        assert result is not None
        assert "password" in result  # pragma: allowlist secret
