import json
from typing import Any, Literal

import pytest
from notte_sdk.client import NotteClient
from notte_sdk.types import PersonaCreateRequest, PersonaResponse
from pydantic import ValidationError

from tests.sdk.test_generated_endpoints import fake


def _persona_response_dict(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "persona_id": "persona_123",
        "status": "active",
        "first_name": "Amy",
        "last_name": "Ferguson",
        "email": "amy.ferguson@example.com",
        "internal_email": "persona_123@example.com",
        "vault_id": None,
        "phone_number": None,
        "created_at": "2026-10-13T00:00:00Z",
    }
    data.update(overrides)
    return data


def test_persona_create_request_email_provider_defaults_to_notte() -> None:
    assert PersonaCreateRequest().email_provider == "notte"


@pytest.mark.parametrize("provider", ["agentmail", "resend"])
def test_persona_create_request_accepts_provider(provider: str) -> None:
    request = PersonaCreateRequest.model_validate({"email_provider": provider})
    assert request.email_provider == provider
    assert json.loads(request.model_dump_json(exclude_none=True))["email_provider"] == provider


def test_persona_create_request_rejects_unknown_email_provider() -> None:
    with pytest.raises(ValidationError):
        _ = PersonaCreateRequest.model_validate({"email_provider": "gmail"})


def test_persona_response_without_email_provider_defaults_to_notte() -> None:
    response = PersonaResponse.model_validate(_persona_response_dict())
    assert response.email_provider == "notte"


@pytest.mark.parametrize("provider", ["agentmail", "resend"])
def test_persona_response_parses_email_provider(provider: Literal["agentmail", "resend"]) -> None:
    response = PersonaResponse.model_validate(_persona_response_dict(email_provider=provider))
    assert response.email_provider == provider


@pytest.mark.parametrize("provider", ["agentmail", "resend"])
def test_personas_create_sends_email_provider(
    provider: Literal["agentmail", "resend"], monkeypatch: pytest.MonkeyPatch
) -> None:
    api = fake(monkeypatch, _persona_response_dict(email_provider=provider))
    client = NotteClient(api_key="test-api-key")

    response = client.personas.create(email_provider=provider)

    assert response.email_provider == provider
    body = json.loads([c for c in api.calls if c.method == "POST"][-1].data)
    assert body["email_provider"] == provider


@pytest.mark.parametrize("provider", ["agentmail", "resend"])
def test_persona_constructor_forwards_email_provider(
    provider: Literal["agentmail", "resend"], monkeypatch: pytest.MonkeyPatch
) -> None:
    api = fake(monkeypatch, _persona_response_dict(email_provider=provider))
    client = NotteClient(api_key="test-api-key")

    persona = client.Persona(email_provider=provider)

    assert persona.info.email_provider == provider
    body = json.loads([c for c in api.calls if c.method == "POST"][-1].data)
    assert body["email_provider"] == provider
