"""Integration tests for AacVault — validates the aac CLI binary is installed and responds correctly.

These tests run by default when the `aac` CLI is available. They do NOT require
a running `aac listen` session — they verify CLI availability, error handling,
and response parsing against the real binary.
"""

import asyncio
import shutil

import pytest
from notte_core.credentials.aac import AacVault

AAC_AVAILABLE = shutil.which("aac") is not None

pytestmark = pytest.mark.skipif(not AAC_AVAILABLE, reason="aac CLI not installed")


def test_aac_vault_starts_without_token() -> None:
    vault = AacVault(token=None)
    vault.start()
    assert vault._paired is False
    vault.stop()


def test_aac_vault_list_credentials_returns_empty() -> None:
    vault = AacVault(token=None)
    vault.start()
    creds = asyncio.run(vault.list_credentials_async())
    assert creds == []
    vault.stop()


def test_aac_vault_get_credentials_returns_none_without_session() -> None:
    """Without a paired session, credential requests should return None gracefully."""
    vault = AacVault(token=None, timeout=5)
    vault.start()
    creds = asyncio.run(vault.get_credentials_async("https://example.com"))
    assert creds is None
    vault.stop()


def test_aac_vault_pairing_fails_with_invalid_token() -> None:
    """An invalid token should raise RuntimeError, not hang."""
    vault = AacVault(token="INVALID99", timeout=10)
    with pytest.raises(RuntimeError, match="aac pairing failed"):
        vault.start()
