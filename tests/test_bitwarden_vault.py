import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest
from notte_core.credentials.base import Credential
from notte_core.credentials.bitwarden import BitwardenVault


def _make_secret_response(secret_id: str, key: str, value: dict, project_id: str = "proj-1") -> MagicMock:
    s = MagicMock()
    s.id = secret_id
    s.key = key
    s.value = json.dumps(value)
    s.project_id = project_id
    s.note = ""
    return s


GITHUB_SECRET = _make_secret_response(
    "00000000-0000-0000-0000-000000000001",
    "GitHub Login",
    {
        "url": "https://github.com/login",
        "password": "gh-pass-123",  # pragma: allowlist secret
        "username": "octocat",
        "email": "octocat@github.com",
    },
)

NOTTE_SECRET = _make_secret_response(
    "00000000-0000-0000-0000-000000000002",
    "Notte",
    {
        "url": "https://app.notte.cc",
        "password": "notte-pass",  # pragma: allowlist secret
        "email": "user@notte.cc",
        "mfa_secret": "JBSWY3DPEHPK3PXP",  # pragma: allowlist secret
    },
)

INVALID_SECRET = _make_secret_response("00000000-0000-0000-0000-000000000003", "Bad Secret", {})
# Override value to be invalid JSON
INVALID_SECRET.value = "not-valid-json"

MISSING_PASSWORD_SECRET = _make_secret_response(
    "00000000-0000-0000-0000-000000000004",
    "No Password",  # pragma: allowlist secret
    {"url": "https://example.com", "username": "test"},
)

ALL_SECRETS = [GITHUB_SECRET, NOTTE_SECRET, INVALID_SECRET, MISSING_PASSWORD_SECRET]


def _mock_client(secrets: list[MagicMock] | None = None) -> MagicMock:
    """Create a mock BitwardenClient with preset secrets."""
    if secrets is None:
        secrets = ALL_SECRETS

    client = MagicMock()

    # Mock auth
    client.auth.return_value.login_access_token.return_value = MagicMock()

    # Mock secrets().list() -> returns identifiers
    list_response = MagicMock()
    list_data = MagicMock()
    list_data.data = [MagicMock(id=s.id) for s in secrets]
    list_response.data = list_data
    client.secrets.return_value.list.return_value = list_response

    # Mock secrets().get_by_ids() -> returns full secrets
    full_response = MagicMock()
    full_data = MagicMock()
    full_data.data = secrets
    full_response.data = full_data
    client.secrets.return_value.get_by_ids.return_value = full_response

    return client


def _mock_get_sdk(secrets: list[MagicMock] | None = None):
    """Return a mock _get_sdk that returns (ClientClass, DeviceType, settings_fn)."""
    client = _mock_client(secrets)
    client_cls = MagicMock(return_value=client)
    device_type = MagicMock()
    settings_fn = MagicMock()
    return client_cls, device_type, settings_fn


@pytest.fixture()
def vault():
    with patch("notte_core.credentials.bitwarden._get_sdk", return_value=_mock_get_sdk()):
        v = BitwardenVault(
            access_token="fake-token",  # pragma: allowlist secret
            organization_id="org-1",
        )
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
    def test_start_validates_sdk_installed(self) -> None:
        with patch("notte_core.credentials.bitwarden._get_sdk", side_effect=ImportError("bitwarden-sdk is required")):
            vault = BitwardenVault(access_token="test")  # pragma: allowlist secret
            with pytest.raises(ImportError, match="bitwarden-sdk is required"):
                vault.start()

    def test_start_validates_token(self) -> None:
        vault = BitwardenVault(access_token="")
        with pytest.raises(ValueError, match="access token required"):
            vault.start()

    def test_context_manager(self) -> None:
        with patch("notte_core.credentials.bitwarden._get_sdk", return_value=_mock_get_sdk()):
            with BitwardenVault(access_token="test", organization_id="org-1") as vault:  # pragma: allowlist secret
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
