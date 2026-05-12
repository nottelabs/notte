"""Integration tests for AacVault — requires real aac CLI + a running aac listen session.

These tests are skipped unless AAC_INTEGRATION_TEST=1 is set and aac is installed.
A cached aac session must exist (run `aac listen` + `aac connect --token <code>` first).

Usage:
    # Terminal 1: Start aac listen
    aac listen

    # Terminal 2: Pair once
    aac connect --token <code-from-terminal-1>

    # Terminal 3: Run tests
    AAC_INTEGRATION_TEST=1 pytest tests/integration/test_aac_vault_integration.py -v
"""

import asyncio
import os
import shutil

import pytest
from notte_core.credentials.aac import AacVault

AAC_ENABLED = os.environ.get("AAC_INTEGRATION_TEST") == "1" and shutil.which("aac") is not None

pytestmark = pytest.mark.skipif(not AAC_ENABLED, reason="AAC_INTEGRATION_TEST=1 not set or aac CLI not installed")


def test_aac_connect_with_cached_session() -> None:
    """Test credential fetch using a cached aac session (no token needed)."""
    vault = AacVault(token=None)
    vault.start()
    creds = asyncio.run(vault.list_credentials_async())
    assert creds == []
    vault.stop()
