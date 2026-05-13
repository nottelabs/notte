"""Integration tests for BitwardenVault — validates the bitwarden-sdk works correctly.

Tests that require a real BWS_ACCESS_TOKEN + BWS_ORGANIZATION_ID are skipped unless
both env vars are set. SDK availability is checked at import time.
"""

import asyncio
import os

import pytest

try:
    from bitwarden_sdk import BitwardenClient  # noqa: F401

    _HAS_SDK = True
except ImportError:
    _HAS_SDK = False

from notte_core.credentials.bitwarden import BitwardenVault

BWS_TOKEN = os.environ.get("BWS_ACCESS_TOKEN", "")
BWS_ORG_ID = os.environ.get("BWS_ORGANIZATION_ID", "")
BWS_AUTHENTICATED = _HAS_SDK and bool(BWS_TOKEN) and bool(BWS_ORG_ID)

pytestmark = pytest.mark.skipif(not _HAS_SDK, reason="bitwarden-sdk not installed")


def test_bws_vault_validates_missing_token() -> None:
    vault = BitwardenVault(access_token="")
    with pytest.raises(ValueError, match="access token required"):
        vault.start()


def test_bws_vault_start_fails_with_invalid_token() -> None:
    vault = BitwardenVault(
        access_token="invalid-token",  # pragma: allowlist secret
        organization_id="invalid-org",
    )
    with pytest.raises(Exception):
        vault.start()


@pytest.mark.skipif(not BWS_AUTHENTICATED, reason="BWS_ACCESS_TOKEN and BWS_ORGANIZATION_ID not set")
def test_list_secrets() -> None:
    with BitwardenVault() as vault:
        creds = asyncio.run(vault.list_credentials_async())
        assert isinstance(creds, list)


@pytest.mark.skipif(not BWS_AUTHENTICATED, reason="BWS_ACCESS_TOKEN and BWS_ORGANIZATION_ID not set")
def test_get_credentials_for_known_domain() -> None:
    with BitwardenVault() as vault:
        creds = asyncio.run(vault.list_credentials_async())
        if len(creds) == 0:
            pytest.skip("No secrets found in BWS project")
        first_url = creds[0].url
        result = asyncio.run(vault.get_credentials_async(first_url))
        assert result is not None
        assert "password" in result  # pragma: allowlist secret
