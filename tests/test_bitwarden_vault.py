import asyncio
import json
import os
import stat
import tempfile

import pytest
from notte_core.credentials.base import Credential
from notte_core.credentials.bitwarden import BitwardenVault

GITHUB_SECRET = {
    "id": "secret-1",
    "key": "GitHub Login",
    "value": json.dumps(
        {
            "url": "https://github.com/login",
            "password": "gh-pass-123",  # pragma: allowlist secret
            "username": "octocat",
            "email": "octocat@github.com",
        }
    ),
}

NOTTE_SECRET = {
    "id": "secret-2",
    "key": "Notte",
    "value": json.dumps(
        {
            "url": "https://app.notte.cc",
            "password": "notte-pass",  # pragma: allowlist secret
            "email": "user@notte.cc",
            "mfa_secret": "JBSWY3DPEHPK3PXP",  # pragma: allowlist secret
        }
    ),
}

INVALID_SECRET = {
    "id": "secret-3",
    "key": "Bad Secret",
    "value": "not-valid-json",
}

MISSING_PASSWORD_SECRET = {
    "id": "secret-4",
    "key": "No Password",
    "value": json.dumps({"url": "https://example.com", "username": "test"}),
}


def _make_fake_bws(secrets: list[dict]) -> str:
    """Create a fake bws script that returns given secrets as JSON."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False)
    f.write(f"#!/bin/bash\necho '{json.dumps(secrets)}'\n")
    f.close()
    os.chmod(f.name, stat.S_IRWXU)
    return f.name


@pytest.fixture()
def fake_bws():
    path = _make_fake_bws([GITHUB_SECRET, NOTTE_SECRET, INVALID_SECRET, MISSING_PASSWORD_SECRET])
    yield path
    os.unlink(path)


@pytest.fixture()
def vault(fake_bws: str):
    v = BitwardenVault(access_token="fake-token", bws_path=fake_bws)
    v.start()
    yield v
    v.stop()


class TestBitwardenVaultGetCredentials:
    def test_finds_credentials_by_domain(self, vault: BitwardenVault) -> None:
        creds = asyncio.run(vault.get_credentials_async("https://github.com/whatever"))
        assert creds is not None
        assert creds["password"] == "gh-pass-123"  # pragma: allowlist secret
        assert creds["username"] == "octocat"

    def test_finds_credentials_with_subdomain(self, vault: BitwardenVault) -> None:
        creds = asyncio.run(vault.get_credentials_async("https://app.notte.cc/dashboard"))
        assert creds is not None
        assert creds["password"] == "notte-pass"  # pragma: allowlist secret

    def test_returns_none_for_unknown_domain(self, vault: BitwardenVault) -> None:
        creds = asyncio.run(vault.get_credentials_async("https://unknown-site.com"))
        assert creds is None

    def test_includes_mfa_secret(self, vault: BitwardenVault) -> None:
        creds = asyncio.run(vault.get_credentials_async("https://notte.cc"))
        assert creds is not None
        assert "mfa_secret" in creds

    def test_tracks_retrieved_credentials(self, vault: BitwardenVault) -> None:
        asyncio.run(vault.get_credentials_async("https://github.com"))
        past = vault.past_credentials()
        assert len(past) == 1


class TestBitwardenVaultListCredentials:
    def test_lists_valid_credentials_only(self, vault: BitwardenVault) -> None:
        cred_list = asyncio.run(vault.list_credentials_async())
        assert len(cred_list) == 2
        urls = {c.url for c in cred_list}
        assert "https://github.com/login" in urls
        assert "https://app.notte.cc" in urls

    def test_returns_credential_objects(self, vault: BitwardenVault) -> None:
        cred_list = asyncio.run(vault.list_credentials_async())
        assert all(isinstance(c, Credential) for c in cred_list)


class TestBitwardenVaultLifecycle:
    def test_start_validates_bws_exists(self) -> None:
        vault = BitwardenVault(access_token="test", bws_path="/nonexistent/bws")
        with pytest.raises(RuntimeError, match="CLI not found"):
            vault.start()

    def test_start_validates_token(self, fake_bws: str) -> None:
        vault = BitwardenVault(access_token="", bws_path=fake_bws)
        with pytest.raises(ValueError, match="access token required"):
            vault.start()

    def test_context_manager(self, fake_bws: str) -> None:
        with BitwardenVault(access_token="test", bws_path=fake_bws) as vault:
            creds = asyncio.run(vault.list_credentials_async())
            assert len(creds) == 2


class TestBitwardenVaultReadOnly:
    def test_credit_card_not_supported(self, vault: BitwardenVault) -> None:
        with pytest.raises(NotImplementedError):
            asyncio.run(
                vault.set_credit_card_async(
                    card_holder_name="Test",
                    card_number="4242",
                    card_cvv="123",
                    card_full_expiration="12/30",
                )
            )

        with pytest.raises(NotImplementedError):
            asyncio.run(vault.get_credit_card_async())

        with pytest.raises(NotImplementedError):
            asyncio.run(vault.delete_credit_card_async())
