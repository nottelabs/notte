"""Vault compatibility captures, first run before migrating the public facade."""

import json
import subprocess
import sys
from typing import Any

import pytest
from notte_core import __version__
from notte_sdk import NotteClient
from notte_sdk.endpoints.vaults import VaultsClient
from notte_sdk.errors import NotteAPIError
from notte_sdk.types import AddCredentialsRequest, AddCreditCardRequest
from pydantic import ValidationError

from tests.sdk.test_generated_endpoints import SERVER, VAULT, fake

CREDS = {"email": "a@example.test", "password": "test-password"}  # pragma: allowlist secret
CARD = {
    "card_holder_name": "Ada",
    "card_number": "4242424242424242",
    "card_cvv": "123",
    "card_full_expiration": "12/30",
}
ID = "a/b ?#%é"
PATH = "/vaults/a%2Fb%20%3F%23%25%C3%A9"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> NotteClient:
    monkeypatch.setattr("notte_sdk.endpoints.base.BaseClient.check_and_warn_version_mismatch", lambda _: None)
    monkeypatch.delenv("NOTTE_DB_PREVIEW_BRANCH", raising=False)
    monkeypatch.delenv("NOTTE_AUTH_CAPABILITY", raising=False)
    scope = sys.modules.get("ci_vault_scope")
    if scope is not None:
        monkeypatch.setattr(scope, "record_vault_id", lambda *_: pytest.fail("Fake vault must not enter CI cleanup"))
        if getattr(scope, "_installed", False):
            monkeypatch.setattr(VaultsClient, "create", getattr(VaultsClient.create, "__wrapped__"))
    return NotteClient(api_key="test-api-key", server_url=SERVER)  # pragma: allowlist secret


def test_vault_wire_contract(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    monkeypatch.setattr("notte_core.telemetry._capture_usage_event", lambda name, **_: events.append(name))
    session = fake(monkeypatch, VAULT)
    assert client.vaults.create().vault_id == "vault-1"
    _ = client.vaults.create(name="named")
    session.payload = {"items": [VAULT], "page": 1, "page_size": 10, "total": 1}
    assert client.vaults.list()[0].for_persona is False
    session.payload = []
    assert client.vaults.list(page=0, page_size=101, only_active=False) == []
    session.payload = {"status": "success"}
    _ = client.vaults.credentials_add(ID, url="https://www.example.com/login", **CREDS)
    _ = client.vaults.credit_card_set(ID, **CARD)
    session.payload = {"credentials": CREDS}
    assert client.vaults.credentials_get(ID, url="https://www.example.com/login").credentials == CREDS
    session.payload = {"credit_card": CARD}
    assert client.vaults.credit_card_get(ID).credit_card == CARD
    session.payload = {"credentials": [{"username": None, "email": "a@example.test", "url": "example.com"}]}
    assert client.vaults.credentials_list(ID).credentials[0].url == "example.com"
    assert client.vaults.get(ID) == ID
    session.payload = {"status": "failure"}
    assert client.vaults.credentials_delete(ID, url="https://www.example.com/login").status == "failure"
    assert client.vaults.credit_card_delete(ID).message == "Credit card deleted successfully"
    assert client.vaults.delete(ID).message == "Vault deleted successfully"
    assert [(c.method, c.url.removeprefix(SERVER), c.params) for c in session.calls] == [
        ("POST", "/vaults/create", {}),
        ("POST", "/vaults/create", {}),
        ("GET", "/vaults", {}),
        ("GET", "/vaults", {"only_active": "False", "page_size": "101", "page": "0"}),
        ("POST", PATH + "/credentials", {}),
        ("POST", PATH + "/card", {}),
        ("GET", PATH + "/credentials", {"url": "https://www.example.com/login"}),
        ("GET", PATH + "/card", {}),
        ("GET", PATH, {}),
        ("GET", PATH, {}),
        ("DELETE", PATH + "/credentials", {"url": "https://www.example.com/login"}),
        ("DELETE", PATH + "/card", {}),
        ("DELETE", PATH, {}),
    ]
    assert [json.loads(c.data) for c in session.calls if c.method == "POST"] == [
        {},
        {"name": "named"},
        {"url": "https://www.example.com/login", "credentials": CREDS},
        {"credit_card": CARD},
    ]
    for call in session.calls:
        assert call.headers == {
            "Authorization": "Bearer test-api-key",  # pragma: allowlist secret
            "x-notte-sdk-version": __version__,
            "x-notte-request-origin": "sdk-python",
            **({"Content-Type": "application/json"} if call.method == "POST" else {}),
        }
    assert events == [
        "cloud.vault." + name
        for name in [
            "create",
            "create",
            "list",
            "list",
            "credentials.add",
            "credit_card.set",
            "credentials.get",
            "credit_card.get",
            "credentials.list",
            "credentials.list",
            "credentials.delete",
            "credit_card.delete",
            "delete",
        ]
    ]


@pytest.mark.parametrize("status", [404, 422])
@pytest.mark.parametrize(
    "method,kwargs",
    [
        ("credentials_get", {"url": "example.com"}),
        ("credentials_delete", {"url": "example.com"}),
        ("delete", {}),
        ("credit_card_get", {}),
        ("credit_card_delete", {}),
        ("credentials_list", {}),
        ("credentials_add", {"url": "example.com", **CREDS}),
        ("credit_card_set", CARD),
    ],
)
def test_vault_errors(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch, status: int, method: str, kwargs: dict[str, Any]
) -> None:
    _ = fake(monkeypatch, {"detail": "vault error"}, status_code=status)
    with pytest.raises(NotteAPIError) as error:
        _ = getattr(client.vaults, method)(ID, **kwargs)
    assert error.value.status_code == status
    assert error.value.error == {"detail": "vault error"}
    assert PATH.lstrip("/") in str(error.value)


@pytest.mark.parametrize("method", ["delete", "credit_card_get", "credit_card_delete", "credentials_list"])
def test_empty_request_keywords_are_sent(client: NotteClient, monkeypatch: pytest.MonkeyPatch, method: str) -> None:
    session = fake(monkeypatch, {"detail": "invalid query"}, status_code=422)
    with pytest.raises(NotteAPIError) as error:
        _ = getattr(client.vaults, method)(ID, typo=True)
    assert error.value.status_code == 422
    assert session.calls[-1].params == {"typo": "True"}


@pytest.mark.parametrize(
    "credentials",
    [
        {"password": CREDS["password"]},  # pragma: allowlist secret
        {**CREDS, "username": "both"},
        {**CREDS, "mfa_secret": "999777"},  # pragma: allowlist secret
        {**CREDS, "email": None},
        {**CREDS, "username": None},
        {**CREDS, "extra": "unknown"},
    ],
)
def test_server_validates_invalid_credentials(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch, credentials: dict[str, Any]
) -> None:
    session = fake(monkeypatch, {"detail": "invalid credentials"}, status_code=422)
    with pytest.raises(NotteAPIError) as error:
        _ = client.vaults.credentials_add(ID, url="example.com", **credentials)
    assert error.value.status_code == 422
    assert error.value.error == {"detail": "invalid credentials"}
    assert json.loads(session.calls[-1].data) == {"url": "example.com", "credentials": credentials}


def test_vault_request_models() -> None:
    request = AddCredentialsRequest.from_dict({"url": "https://www.example.com/login", **CREDS})  # pyright: ignore[reportArgumentType]
    assert request.credentials == CREDS
    assert request.model_dump() == {"url": "example.com", "credentials": CREDS}
    assert AddCreditCardRequest.from_dict(CARD).credit_card == CARD  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize("data", [{"url": ""}, {"url": "example.com", "typo": True}, {}])
def test_server_validates_url(client: NotteClient, monkeypatch: pytest.MonkeyPatch, data: dict[str, Any]) -> None:
    session = fake(monkeypatch, {"detail": "invalid URL"}, status_code=422)
    with pytest.raises(NotteAPIError) as error:
        _ = client.vaults.credentials_get(ID, **data)
    assert error.value.status_code == 422
    assert session.calls[-1].params == {key: str(value) for key, value in data.items()}


@pytest.mark.parametrize("credentials", [{"password": CREDS["password"]}, {**CREDS, "username": "both"}])
def test_responses_do_not_repeat_identity_validation(
    client: NotteClient, monkeypatch: pytest.MonkeyPatch, credentials: dict[str, Any]
) -> None:
    _ = fake(monkeypatch, {"credentials": credentials})
    assert client.vaults.credentials_get(ID, url="example.com").credentials == credentials


def test_response_schema_is_still_validated(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = fake(monkeypatch, {"credentials": {"email": None}})
    with pytest.raises(ValidationError):
        _ = client.vaults.credentials_get(ID, url="example.com")


def test_secret_values_are_unmasked_only_for_transport(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic import SecretStr

    secret = SecretStr("synthetic-vault-password")  # pragma: allowlist secret
    session = fake(monkeypatch, {"status": "success"})
    _ = client.vaults.credentials_add(ID, url="example.com", username="ada", password=secret)  # pyright: ignore[reportArgumentType]
    assert json.loads(session.calls[-1].data)["credentials"]["password"] == secret.get_secret_value()
    assert secret.get_secret_value() not in repr(secret)


def test_vault_models_are_generated() -> None:
    from notte_sdk._generated import models
    from notte_sdk.types import (
        DeleteCredentialsRequest,
        GetCredentialsRequest,
        GetCredentialsResponse,
        GetCreditCardResponse,
        Vault,
    )

    assert GetCredentialsRequest is models.VaultCredentialsGetParametersQuery
    assert DeleteCredentialsRequest is models.VaultCredentialsDeleteParametersQuery
    assert Vault is models.Vault
    from notte_core import types as core

    assert AddCredentialsRequest is core.AddCredentialsRequest
    assert AddCreditCardRequest is core.AddCreditCardRequest
    assert GetCredentialsResponse is core.GetCredentialsResponse
    assert GetCreditCardResponse is core.GetCreditCardResponse


def test_shared_vault_helper_keeps_core_credentials(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from notte_core.credentials.base import Credential

    session = fake(monkeypatch, {"credentials": []})
    vault = client.Vault(vault_id=ID)
    session.payload = {"credentials": [{"username": "ada", "email": None, "url": "example.com"}]}
    credentials = vault.list_credentials()
    assert len(credentials) == 1
    assert type(credentials[0]) is Credential
    assert credentials[0].username == "ada"


def test_vault_helper_sends_invalid_mfa_to_api(client: NotteClient, monkeypatch: pytest.MonkeyPatch) -> None:
    session = fake(monkeypatch, {"credentials": []})
    vault = client.Vault(vault_id=ID)
    session.payload = {"detail": "Invalid MFA secret code"}
    session.status_code = 422
    with pytest.raises(NotteAPIError) as error:
        vault.add_credentials(url="example.com", **CREDS, mfa_secret="999777")  # pragma: allowlist secret
    assert error.value.status_code == 422
    assert json.loads(session.calls[-1].data)["credentials"]["mfa_secret"] == "999777"


def test_vault_credential_helper_preserves_profiling() -> None:
    # Enable profiling before SDK decorators are evaluated without changing the
    # test runner's imports or global profiler.
    script = """
import asyncio
from unittest.mock import AsyncMock, Mock
from notte_core.profiling import profiler
profiler.enable = True
from notte_sdk.endpoints.vaults import NotteVault, AsyncNotteVault

client = Mock()
client.get.return_value = "fake-vault"
for asynchronous in (False, True):
    client = AsyncMock() if asynchronous else Mock()
    client.get.return_value = "fake-vault"
    vault = (AsyncNotteVault if asynchronous else NotteVault)(vault_id="fake-vault", _client=client)
    for fails in (False, True):
        profiler.memory_exporter.clear()
        client.credentials_add.side_effect = ValueError("API failure") if fails else None
        try:
            if asynchronous:
                asyncio.run(vault.add_credentials("example.com", username="ada"))
            else:
                vault.add_credentials("example.com", username="ada")
        except ValueError:
            assert fails
        else:
            assert not fails
        spans = [
            span for span in profiler.memory_exporter.get_finished_spans()
            if span.name == "BaseVault.add_credentials_async"
        ]
        assert len(spans) == 1, spans
        assert spans[0].end_time >= spans[0].start_time
        assert spans[0].status.status_code.name == ("ERROR" if fails else "UNSET")
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
