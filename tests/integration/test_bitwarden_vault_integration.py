"""BitwardenVault against the real Bitwarden Secrets Manager.

The tests reading secrets need a machine account: set BWS_ACCESS_TOKEN and BWS_ORGANIZATION_ID, with at
least one secret in the notte credential format readable by that account.
"""

import os

import pytest
from notte_core.credentials.bitwarden import BitwardenVault

BWS_AUTHENTICATED = bool(os.environ.get("BWS_ACCESS_TOKEN")) and bool(os.environ.get("BWS_ORGANIZATION_ID"))


def test_start_fails_with_an_unknown_token() -> None:
    vault = BitwardenVault(
        access_token="0.4ae1d9e2-0000-0000-0000-000000000000.notte:YWJjZGVmZ2hpamtsbW5vcA==",  # pragma: allowlist secret
        organization_id="11111111-1111-1111-1111-111111111111",
    )
    with pytest.raises(Exception, match="invalid_client"):
        vault.start()


@pytest.mark.skipif(not BWS_AUTHENTICATED, reason="BWS_ACCESS_TOKEN and BWS_ORGANIZATION_ID not set")
def test_reads_credentials() -> None:
    with BitwardenVault() as vault:
        creds = vault.list_credentials()
        assert len(creds) > 0, "no secret in the notte credential format"
        result = vault.get_credentials(creds[0].url)
        assert result is not None
        assert result["password"]  # pragma: allowlist secret
