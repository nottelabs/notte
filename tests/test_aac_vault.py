import asyncio
import json
import os
import stat
import tempfile

import pytest
from notte_core.credentials.aac import AacVault


def _make_fake_aac(credential: dict | None = None, fail: bool = False) -> str:
    """Create a fake aac script that simulates the aac CLI."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False)

    if fail:
        f.write(
            "#!/bin/bash\n"
            'echo \'{"error":{"code":"general_error","message":"connection failed"},"success":false}\'\n'
            "exit 2\n"
        )
    else:
        cred = credential or {
            "username": "octocat",
            "password": "gh-secret-123",  # pragma: allowlist secret
            "totp": "654321",
            "uri": "https://github.com",
            "notes": None,
        }
        success_response = json.dumps(
            {
                "credential": cred,
                "domain": "github.com",
                "success": True,
            }
        )
        pairing_response = json.dumps({"success": True})
        # Return pairing response if --token is present, credential otherwise
        f.write(
            "#!/bin/bash\n"
            f'if echo "$@" | grep -q "\\-\\-domain"; then\n'
            f"  echo '{success_response}'\n"
            f"  exit 0\n"
            f"fi\n"
            f"echo '{pairing_response}'\n"
            f"exit 0\n"
        )

    f.close()
    os.chmod(f.name, stat.S_IRWXU)
    return f.name


@pytest.fixture()
def fake_aac():
    path = _make_fake_aac()
    yield path
    os.unlink(path)


@pytest.fixture()
def fake_aac_fail():
    path = _make_fake_aac(fail=True)
    yield path
    os.unlink(path)


@pytest.fixture()
def vault(fake_aac: str):
    v = AacVault(token="ABC-DEF-123", aac_path=fake_aac)
    v.start()
    yield v
    v.stop()


class TestAacVaultGetCredentials:
    def test_fetches_credential_by_domain(self, vault: AacVault) -> None:
        creds = asyncio.run(vault.get_credentials_async("https://github.com/login"))
        assert creds is not None
        assert creds["password"] == "gh-secret-123"  # pragma: allowlist secret
        assert creds["username"] == "octocat"

    def test_returns_totp_as_mfa_secret(self, vault: AacVault) -> None:
        creds = asyncio.run(vault.get_credentials_async("https://github.com"))
        assert creds is not None
        assert creds["mfa_secret"] == "654321"

    def test_bypasses_totp_generation(self, vault: AacVault) -> None:
        """AacVault overrides get_credentials_async to skip TOTP().now() —
        aac returns live codes, not base32 secrets."""
        creds = asyncio.run(vault.get_credentials_async("https://github.com"))
        assert creds is not None
        # The raw TOTP code should be returned as-is, not processed
        assert creds["mfa_secret"] == "654321"

    def test_tracks_credentials_for_screenshot_masking(self, vault: AacVault) -> None:
        asyncio.run(vault.get_credentials_async("https://github.com"))
        past = vault.past_credentials()
        assert len(past) == 1
        assert "https://github.com" in past

    def test_returns_none_on_failure(self, fake_aac_fail: str) -> None:
        vault = AacVault(token=None, aac_path=fake_aac_fail)
        vault.start()  # no pairing since token=None
        creds = asyncio.run(vault.get_credentials_async("https://github.com"))
        assert creds is None
        vault.stop()

    def test_handles_credential_without_totp(self) -> None:
        path = _make_fake_aac(
            credential={
                "username": "user",
                "password": "pass",  # pragma: allowlist secret
                "totp": None,
                "uri": "https://example.com",
                "notes": None,
            }
        )
        try:
            vault = AacVault(token="ABC-DEF-123", aac_path=path)
            vault.start()
            creds = asyncio.run(vault.get_credentials_async("https://example.com"))
            assert creds is not None
            assert creds["password"] == "pass"  # pragma: allowlist secret
            assert "mfa_secret" not in creds
            vault.stop()
        finally:
            os.unlink(path)

    def test_handles_credential_without_username(self) -> None:
        path = _make_fake_aac(
            credential={
                "username": None,
                "password": "pass",  # pragma: allowlist secret
                "totp": None,
                "uri": None,
                "notes": None,
            }
        )
        try:
            vault = AacVault(token="ABC-DEF-123", aac_path=path)
            vault.start()
            creds = asyncio.run(vault.get_credentials_async("https://example.com"))
            assert creds is not None
            assert creds["password"] == "pass"  # pragma: allowlist secret
            assert "username" not in creds
            vault.stop()
        finally:
            os.unlink(path)


class TestAacVaultPairing:
    def test_pairs_on_start_when_token_provided(self, fake_aac: str) -> None:
        vault = AacVault(token="ABC-DEF-123", aac_path=fake_aac)
        vault.start()
        assert vault._paired is True
        vault.stop()

    def test_skips_pairing_when_no_token(self, fake_aac: str) -> None:
        vault = AacVault(token=None, aac_path=fake_aac)
        vault.start()
        assert vault._paired is False
        vault.stop()

    def test_pairing_failure_raises(self, fake_aac_fail: str) -> None:
        vault = AacVault(token="ABC-DEF-123", aac_path=fake_aac_fail)
        with pytest.raises(RuntimeError, match="aac pairing failed"):
            vault.start()

    def test_reads_token_from_env(self, fake_aac: str) -> None:
        os.environ["AAC_TOKEN"] = "ENV-TOK-123"
        try:
            vault = AacVault(aac_path=fake_aac)
            assert vault.token == "ENV-TOK-123"
        finally:
            del os.environ["AAC_TOKEN"]


class TestAacVaultLifecycle:
    def test_start_validates_aac_exists(self) -> None:
        vault = AacVault(token="test", aac_path="/nonexistent/aac")
        with pytest.raises(RuntimeError, match="CLI not found"):
            vault.start()

    def test_context_manager(self, fake_aac: str) -> None:
        with AacVault(token="ABC-DEF-123", aac_path=fake_aac) as vault:
            assert vault._paired is True
        assert vault._paired is False


class TestAacVaultReadOnly:
    def test_add_credentials_raises(self, vault: AacVault) -> None:
        with pytest.raises(NotImplementedError, match="read-only"):
            asyncio.run(vault._add_credentials("https://example.com", {"password": "test"}))  # pragma: allowlist secret

    def test_delete_credentials_raises(self, vault: AacVault) -> None:
        with pytest.raises(NotImplementedError, match="read-only"):
            asyncio.run(vault.delete_credentials_async("https://example.com"))

    def test_list_credentials_returns_empty(self, vault: AacVault) -> None:
        creds = asyncio.run(vault.list_credentials_async())
        assert creds == []

    def test_credit_card_not_supported(self, vault: AacVault) -> None:
        with pytest.raises(NotImplementedError):
            asyncio.run(
                vault.set_credit_card_async(
                    card_holder_name="Test",
                    card_number="4242",
                    card_cvv="123",
                    card_full_expiration="12/30",
                )
            )
