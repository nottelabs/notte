import asyncio
import datetime as dt
import json
import sys
import threading
import uuid
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pyotp
import pytest
from bitwarden_sdk import SecretResponse
from notte_core.credentials.base import Credential
from notte_core.credentials.bitwarden import BitwardenVault

ORG_ID = "11111111-1111-1111-1111-111111111111"
PROJECT_ID = "22222222-2222-2222-2222-222222222222"
SEED = "JBSWY3DPEHPK3PXP"  # pragma: allowlist secret


def _secret(key: str, value: str) -> SecretResponse:
    now = dt.datetime.now(dt.timezone.utc)
    return SecretResponse(
        creation_date=now,
        id=uuid.uuid4(),
        key=key,
        note="",
        organization_id=uuid.UUID(ORG_ID),
        revision_date=now,
        value=value,
        project_id=uuid.UUID(PROJECT_ID),
    )


GITHUB = _secret(
    "GitHub Login",
    json.dumps(
        {
            "url": "https://github.com/login",
            "password": "gh-pass-123",  # pragma: allowlist secret
            "username": "octocat",
            "email": "octocat@github.com",
        }
    ),
)
NOTTE = _secret(
    "Notte",
    json.dumps(
        {
            "url": "https://console.notte.cc",
            "password": "notte-pass",  # pragma: allowlist secret
            "email": "user@notte.cc",
            "mfa_secret": SEED,
        }
    ),
)
INVALID_JSON = _secret("Bad Secret", "not-valid-json")
NOT_AN_OBJECT = _secret("List Secret", '["https://example.com"]')
MISSING_PASSWORD = _secret("No Password", json.dumps({"url": "https://example.com", "username": "test"}))
ALL_SECRETS = [GITHUB, NOTTE, INVALID_JSON, NOT_AN_OBJECT, MISSING_PASSWORD]


def _mock_client(secrets: list[SecretResponse]) -> MagicMock:
    """A BitwardenClient whose organization holds `secrets`."""
    client = MagicMock()
    secrets_client = client.secrets.return_value
    secrets_client.list.return_value.data.data = [MagicMock(id=s.id) for s in secrets]
    secrets_client.get_by_ids.return_value.data.data = secrets
    return client


@pytest.fixture()
def client() -> MagicMock:
    return _mock_client(ALL_SECRETS)


@pytest.fixture()
def vault(client: MagicMock) -> Iterator[BitwardenVault]:
    with patch("bitwarden_sdk.BitwardenClient", return_value=client):
        with BitwardenVault(
            access_token="fake-token",  # pragma: allowlist secret
            organization_id=ORG_ID,
            project_id=PROJECT_ID,
        ) as v:
            yield v


class TestBitwardenVaultGetCredentials:
    @pytest.mark.parametrize("target", ["", "https://", "http://.com"])
    def test_domainless_targets_cannot_retrieve_or_delete_a_secret(self, client: MagicMock, target: str) -> None:
        invalid = _secret("Malformed URL", json.dumps({"url": "https://", "password": "unrelated"}))
        client.secrets.return_value.get_by_ids.return_value.data.data = [invalid]
        with patch("bitwarden_sdk.BitwardenClient", return_value=client):
            with BitwardenVault(access_token="test", organization_id=ORG_ID) as vault:
                assert vault.get_credentials(target) is None
                assert not vault.has_credential(target)
                with pytest.raises(ValueError, match="No credentials found"):
                    vault.delete_credentials(target)
                client.secrets.return_value.delete.assert_not_called()

    def test_prefers_an_exact_url_to_another_secret_on_the_domain(self, client: MagicMock) -> None:
        other = _secret("Other GitHub", json.dumps({"url": "https://github.com/settings", "password": "other"}))
        client.secrets.return_value.get_by_ids.return_value.data.data = [GITHUB, other]
        with patch("bitwarden_sdk.BitwardenClient", return_value=client):
            with BitwardenVault(access_token="test", organization_id=ORG_ID) as vault:
                expected = {"password": "other"}  # pragma: allowlist secret
                assert vault.get_credentials("https://github.com/settings") == expected

    def test_finds_credentials_by_domain(self, vault: BitwardenVault) -> None:
        creds = asyncio.run(vault.get_credentials_async("https://github.com/whatever"))
        assert creds == {
            "password": "gh-pass-123",  # pragma: allowlist secret
            "username": "octocat",
            "email": "octocat@github.com",
        }

    def test_finds_credentials_with_subdomain(self, vault: BitwardenVault) -> None:
        creds = asyncio.run(vault.get_credentials_async("https://app.notte.cc/dashboard"))
        assert creds is not None
        assert creds["password"] == "notte-pass"  # pragma: allowlist secret

    def test_returns_none_for_unknown_domain(self, vault: BitwardenVault) -> None:
        assert asyncio.run(vault.get_credentials_async("https://unknown-site.com")) is None

    def test_presence_uses_the_same_domain_match_as_retrieval(self, vault: BitwardenVault) -> None:
        assert vault.has_credential("https://gist.github.com/other")
        assert not vault.has_credential("https://unknown-site.com")

    def test_turns_mfa_secret_into_a_code(self, vault: BitwardenVault) -> None:
        creds = asyncio.run(vault.get_credentials_async("https://notte.cc"))
        assert creds is not None
        assert pyotp.TOTP(SEED).verify(creds["mfa_secret"], valid_window=1)

    def test_tracks_retrieved_credentials(self, vault: BitwardenVault) -> None:
        _ = asyncio.run(vault.get_credentials_async("https://github.com"))
        assert list(vault.past_credentials()) == ["https://github.com"]

    def test_reads_secrets_once(self, vault: BitwardenVault, client: MagicMock) -> None:
        _ = asyncio.run(vault.get_credentials_async("https://github.com"))
        _ = asyncio.run(vault.get_credentials_async("https://notte.cc"))
        assert client.secrets.return_value.get_by_ids.call_count == 1


class TestBitwardenVaultListCredentials:
    def test_lists_valid_credentials_only(self, vault: BitwardenVault) -> None:
        assert vault.list_credentials() == [
            Credential(url="https://github.com/login", username="octocat", email="octocat@github.com"),
            Credential(url="https://console.notte.cc", username=None, email="user@notte.cc"),
        ]

    def test_empty_organization(self) -> None:
        client = _mock_client([])
        with patch("bitwarden_sdk.BitwardenClient", return_value=client):
            with BitwardenVault(access_token="test", organization_id=ORG_ID) as vault:  # pragma: allowlist secret
                assert vault.list_credentials() == []
        client.secrets.return_value.get_by_ids.assert_not_called()


class TestBitwardenVaultWrites:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("operation", ["add", "delete"])
    async def test_an_inflight_refresh_does_not_overwrite_a_write_invalidation(
        self, vault: BitwardenVault, client: MagicMock, operation: str
    ) -> None:
        added = _secret("New", json.dumps({"url": "https://example.com", "password": "new"}))
        stored = [GITHUB, NOTTE]
        started, release = threading.Event(), threading.Event()
        secrets_client = client.secrets.return_value

        def list_secrets(_organization_id: str) -> MagicMock:
            return MagicMock(data=MagicMock(data=[MagicMock(id=secret.id) for secret in stored]))

        def get_secrets(ids: list[uuid.UUID]) -> MagicMock:
            snapshot = [secret for secret in stored if secret.id in ids]
            if not started.is_set():
                started.set()
                assert release.wait(5), "refresh was not released"
            return MagicMock(data=MagicMock(data=snapshot))

        def create_secret(
            _organization_id: uuid.UUID, _key: str, _value: str, _note: None, _project_ids: list[uuid.UUID]
        ) -> MagicMock:
            stored.append(added)
            return MagicMock()

        def delete_secret(ids: list[str]) -> MagicMock:
            stored[:] = [secret for secret in stored if str(secret.id) not in ids]
            return MagicMock()

        secrets_client.list.side_effect = list_secrets
        secrets_client.get_by_ids.side_effect = get_secrets
        secrets_client.create.side_effect = create_secret
        secrets_client.delete.side_effect = delete_secret
        vault._secrets_cache = None
        reading = asyncio.create_task(vault.list_credentials_async())
        try:
            assert await asyncio.to_thread(started.wait, 2)
            if operation == "add":
                await vault.add_credentials_async("https://example.com", password="new")  # pragma: allowlist secret
            else:
                await vault.delete_credentials_async("https://github.com/login")
        finally:
            release.set()
        expected = {json.loads(secret.value)["url"] for secret in stored}
        assert {credential.url for credential in await reading} == expected
        assert {credential.url for credential in await vault.list_credentials_async()} == expected

    @pytest.mark.parametrize("target", ["https://github.com/settings", "https://github.com/other"])
    def test_delete_does_not_choose_the_first_same_domain_secret(self, client: MagicMock, target: str) -> None:
        other = _secret("Other GitHub", json.dumps({"url": "https://github.com/settings", "password": "other"}))
        client.secrets.return_value.get_by_ids.return_value.data.data = [GITHUB, other]
        with patch("bitwarden_sdk.BitwardenClient", return_value=client):
            with BitwardenVault(access_token="test", organization_id=ORG_ID) as vault:
                if target.endswith("settings"):
                    vault.delete_credentials(target)
                    client.secrets.return_value.delete.assert_called_once_with([str(other.id)])
                else:
                    with pytest.raises(ValueError, match="[Aa]mbiguous"):
                        vault.delete_credentials(target)
                    client.secrets.return_value.delete.assert_not_called()

    def test_delete_rejects_duplicate_exact_urls(self, client: MagicMock) -> None:
        duplicate = _secret("Duplicate", GITHUB.value)
        client.secrets.return_value.get_by_ids.return_value.data.data = [GITHUB, duplicate]
        with patch("bitwarden_sdk.BitwardenClient", return_value=client):
            with BitwardenVault(access_token="test", organization_id=ORG_ID) as vault:
                with pytest.raises(ValueError, match="[Aa]mbiguous"):
                    vault.delete_credentials("https://github.com/login")
                client.secrets.return_value.delete.assert_not_called()

    def test_add_credentials_creates_a_secret_and_rereads(self, vault: BitwardenVault, client: MagicMock) -> None:
        vault.add_credentials("https://example.com", username="new", password="new-pass")  # pragma: allowlist secret

        org_id, key, value, note, project_ids = client.secrets.return_value.create.call_args.args
        assert (org_id, key, note, project_ids) == (
            uuid.UUID(ORG_ID),
            "https://example.com",
            None,
            [uuid.UUID(PROJECT_ID)],
        )
        assert json.loads(value) == {
            "url": "https://example.com",
            "username": "new",
            "password": "new-pass",  # pragma: allowlist secret
        }

        # the next reads fetch the secrets again, once
        _ = vault.list_credentials()
        _ = vault.list_credentials()
        assert client.secrets.return_value.get_by_ids.call_count == 2

    def test_add_credentials_requires_a_project(self, client: MagicMock) -> None:
        with patch("bitwarden_sdk.BitwardenClient", return_value=client):
            with BitwardenVault(access_token="test", organization_id=ORG_ID) as vault:  # pragma: allowlist secret
                with pytest.raises(ValueError, match="project_id required"):
                    vault.add_credentials("https://example.com", password="p")  # pragma: allowlist secret

    def test_delete_credentials_deletes_the_matching_secret(self, vault: BitwardenVault, client: MagicMock) -> None:
        vault.delete_credentials("https://github.com")
        client.secrets.return_value.delete.assert_called_once_with([str(GITHUB.id)])

    def test_delete_unknown_credentials_raises(self, vault: BitwardenVault) -> None:
        with pytest.raises(ValueError, match="No credentials found"):
            vault.delete_credentials("https://unknown-site.com")


class TestBitwardenVaultLifecycle:
    def test_start_requires_the_sdk(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(sys.modules, "bitwarden_sdk", None)
        vault = BitwardenVault(access_token="test", organization_id=ORG_ID)  # pragma: allowlist secret
        with pytest.raises(ImportError, match=r"notte-core\[bitwarden\]"):
            vault.start()

    def test_start_validates_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BWS_ACCESS_TOKEN", raising=False)
        with pytest.raises(ValueError, match="access token required"):
            BitwardenVault(organization_id=ORG_ID).start()

    def test_start_validates_organization(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BWS_ORGANIZATION_ID", raising=False)
        with pytest.raises(ValueError, match="organization id required"):
            BitwardenVault(access_token="test").start()  # pragma: allowlist secret

    def test_reads_settings_from_env(self, monkeypatch: pytest.MonkeyPatch, client: MagicMock) -> None:
        monkeypatch.setenv("BWS_ACCESS_TOKEN", "env-token")  # pragma: allowlist secret
        monkeypatch.setenv("BWS_ORGANIZATION_ID", ORG_ID)
        with patch("bitwarden_sdk.BitwardenClient", return_value=client):
            with BitwardenVault():
                pass
        client.auth.return_value.login_access_token.assert_called_once_with("env-token")
        client.secrets.return_value.list.assert_called_once_with(ORG_ID)

    def test_requires_start(self) -> None:
        vault = BitwardenVault(access_token="test", organization_id=ORG_ID)  # pragma: allowlist secret
        with pytest.raises(RuntimeError, match="not started"):
            _ = vault.list_credentials()


class TestBitwardenVaultCreditCard:
    def test_credit_card_not_supported(self, vault: BitwardenVault) -> None:
        with pytest.raises(NotImplementedError):
            vault.set_credit_card(
                card_holder_name="Test", card_number="4242", card_cvv="123", card_full_expiration="12/30"
            )
        with pytest.raises(NotImplementedError):
            _ = vault.get_credit_card()
        with pytest.raises(NotImplementedError):
            vault.delete_credit_card()
