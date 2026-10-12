"""Contract between the generated wire models and the public types in notte_sdk.types."""

import datetime as dt

import pytest
from notte_sdk import types
from notte_sdk._generated import models as wire
from notte_sdk._generated import typeddicts as wire_dicts
from pydantic import BaseModel

# Public model -> generated model it is built on.
BUILT_ON_GENERATED: dict[type[BaseModel], type[BaseModel]] = {
    types.PersonaCreateRequest: wire.PersonaCreateRequest,
    types.PersonaResponse: wire.PersonaResponse,
    types.DeletePersonaResponse: wire.DeletePersonaResponse,
    types.EmailResponse: wire.EmailResponse,
    types.SMSResponse: wire.SMSResponse,
    types.SessionResponse: wire.SessionResponse,
}


@pytest.mark.parametrize("public, generated", BUILT_ON_GENERATED.items(), ids=lambda c: c.__name__)
def test_public_model_extends_generated_model(public: type[BaseModel], generated: type[BaseModel]) -> None:
    assert issubclass(public, generated)
    # The public import path is unchanged.
    assert public.__module__ == "notte_sdk.types"
    # The public model may add client-side fields, never drop wire fields.
    assert set(generated.model_fields) <= set(public.model_fields)


@pytest.mark.parametrize("public", [types.PersonaCreateRequest, types.PersonaResponse, types.EmailResponse])
def test_request_and_response_extra_handling(public: type[BaseModel]) -> None:
    extra = public.model_config.get("extra")
    if issubclass(public, types.SdkRequest):
        assert extra == "forbid"
    else:
        # Responses must tolerate fields the API adds after this SDK was released.
        assert extra in (None, "ignore", "allow")


def test_persona_response_ignores_fields_added_by_the_api() -> None:
    response = types.PersonaResponse.model_validate(
        {
            "persona_id": "p",
            "status": "active",
            "first_name": "A",
            "last_name": "B",
            "email": "a@b.c",
            "internal_email": "p@b.c",
            "vault_id": None,
            "phone_number": None,
            "created_at": "2026-01-01T00:00:00Z",
            "field_from_a_newer_api": 1,
        }
    )
    assert response.created_at == dt.datetime(2026, 1, 1, tzinfo=dt.UTC)


def test_persona_create_kwargs_match_the_request_model() -> None:
    assert set(types.PersonaCreateRequestDict.__annotations__) == set(types.PersonaCreateRequest.model_fields)
    assert set(wire_dicts.PersonaCreateRequest.__annotations__) <= set(types.PersonaCreateRequestDict.__annotations__)
    assert types.PersonaCreateRequest.model_validate({"name": "Ada"}).name == "Ada"
