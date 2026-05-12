"""Integration tests for BitwardenVault — requires real bws CLI + BWS_ACCESS_TOKEN.

These tests are skipped unless BWS_ACCESS_TOKEN is set in the environment.

Usage:
    BWS_ACCESS_TOKEN="0.your-token..." pytest tests/integration/test_bitwarden_vault_integration.py -v
"""

import asyncio
import os
import shutil

import pytest
from notte_core.credentials.bitwarden import BitwardenVault

BWS_TOKEN = os.environ.get("BWS_ACCESS_TOKEN", "")
BWS_AVAILABLE = bool(BWS_TOKEN) and shutil.which("bws") is not None

pytestmark = pytest.mark.skipif(not BWS_AVAILABLE, reason="BWS_ACCESS_TOKEN not set or bws CLI not installed")


def test_list_secrets() -> None:
    with BitwardenVault() as vault:
        creds = asyncio.run(vault.list_credentials_async())
        assert isinstance(creds, list)


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
