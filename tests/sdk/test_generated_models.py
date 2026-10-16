"""The side-by-side models are complete/importable; shared domain identity is preserved."""

import inspect
import json
from pathlib import Path

import pytest
from notte_core import types as core
from notte_sdk import types as public
from notte_sdk._generated import models
from pydantic import BaseModel, ValidationError

ROOT = Path(__file__).parents[2]


def test_every_component_has_an_importable_generated_type() -> None:
    spec = json.loads((ROOT / "openapi/openapi.json").read_text())
    index = json.loads((ROOT / "packages/notte-sdk/src/notte_sdk/_generated/schema_index.json").read_text())
    for name in spec["components"]["schemas"]:
        assert inspect.isclass(getattr(models, index[f"#/components/schemas/{name}"]))
    for cls in vars(models).values():
        if inspect.isclass(cls) and issubclass(cls, BaseModel) and cls.__module__ == models.__name__:
            assert cls.__pydantic_complete__
            assert cls.model_json_schema()  # resolve every forward ref and discriminated union


def test_unmigrated_and_page_operation_types_still_reexport_core() -> None:
    for name, cls in vars(core).items():
        if not name.startswith("_") and name not in {
            "SessionStartRequest",
            "SessionStartRequestDict",
            "SessionResponse",
            "SessionListRequest",
            "SessionListRequestDict",
            "WebSocketUrls",
            "TabSessionDebugResponse",
            "ManagedAuthOperation",
            "SessionStopRequest",
            "SessionStopRequestDict",
            "SessionAuthResponse",
            "SessionDebugResponse",
            "SessionOffsetResponse",
            "ReplayResponse",
            "Cookie",
            "GetCookiesResponse",
            "SetCookiesRequest",
            "SetCookiesResponse",
            "SessionProfile",
            "SessionProfileDict",
            "NotteProxy",
            "NotteProxyDict",
            "ExternalProxy",
            "ExternalProxyDict",
            "TailnetProxy",
            "TailnetProxyDict",
            "ProxySettings",
            "ProxySettingsDict",
            "CreateFunctionRequest",
            "CreateFunctionRequestDict",
            "UpdateFunctionRequest",
            "UpdateFunctionRequestDict",
            "GetFunctionRequest",
            "GetFunctionRequestDict",
            "GetFunctionResponse",
            "GetFunctionWithLinkResponse",
            "DeleteFunctionResponse",
            "ListFunctionsRequest",
            "ListFunctionsRequestDict",
            "ListFunctionsResponse",
            "FunctionRunUpdateRequest",
            "FunctionRunUpdateRequestDict",
            "GetFunctionRunResponse",
            "FunctionRunListItemResponse",
            "ListFunctionRunsRequest",
            "ListFunctionRunsRequestDict",
            "ListFunctionRunsResponse",
            "UpdateFunctionRunResponse",
            "FileSource",
            "SessionFile",
            "SessionFilesPage",
            "PersonaCreateRequest",
            "PersonaCreateRequestDict",
            "PersonaListRequest",
            "PersonaListRequestDict",
            "PersonaResponse",
            "DeletePersonaResponse",
            "MessageReadRequest",
            "MessageReadRequestDict",
            "EmailResponse",
            "SMSResponse",
            "ProfileCreateRequest",
            "ProfileCreateRequestDict",
            "ProfileListRequest",
            "ProfileListRequestDict",
            "ProfileResponse",
            "AddCredentialsRequest",
            "AddCreditCardRequest",
            "DeleteCredentialsRequest",
            "DeleteCredentialsResponse",
            "DeleteCreditCardRequest",
            "DeleteCreditCardResponse",
            "DeleteVaultRequest",
            "DeleteVaultResponse",
            "GetCredentialsRequest",
            "GetCredentialsResponse",
            "GetCreditCardRequest",
            "GetCreditCardResponse",
            "ListCredentialsRequest",
            "VaultListRequest",
            "AddCredentialsResponse",
            "AddCreditCardResponse",
            "Credential",
            "ListCredentialsResponse",
            "Vault",
            "VaultCreateRequest",
            "AddCredentialsRequestDict",
            "AddCreditCardRequestDict",
            "CredentialsDict",
            "CreditCardDict",
            "DeleteCredentialsRequestDict",
            "DeleteCreditCardRequestDict",
            "DeleteVaultRequestDict",
            "GetCredentialsRequestDict",
            "GetCreditCardRequestDict",
            "ListCredentialsRequestDict",
            "VaultCreateRequestDict",
            "VaultListRequestDict",
        }:
            assert getattr(public, name) is cls
    assert issubclass(public.ProfileResponse, models.ProfileResponse)
    assert public.ProfileResponse is not core.ProfileResponse
    assert public.ProfileCreateRequest is models.ProfileCreateRequest
    assert issubclass(public.ProfileListRequest, models.ProfileListParametersQuery)


def test_generated_requests_forbid_extra_fields_and_preserve_constraints() -> None:
    assert models.ProfileCreateRequest(name="test").model_dump() == {"name": "test"}
    with pytest.raises(ValidationError, match="extra_forbidden"):
        models.ProfileCreateRequest.model_validate({"name": "test", "typo": 1})
    assert models.ProfileListParametersQuery().page == 1
    with pytest.raises(ValidationError):
        models.ProfileListParametersQuery(page=0)
    with pytest.raises(ValidationError):
        models.ProfileListParametersQuery(page_size=101)


def test_required_nullable_profile_name_and_missing_array_default() -> None:
    payload = {
        "profile_id": "notte-profile-1234567890123456",
        "name": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    profile = models.ProfileResponse.model_validate(payload)
    assert profile.name is None
    # The snapshot doesn't encode core's default_factory=list. Do not silently patch generation.
    assert profile.persisted_domains is None
    assert core.ProfileResponse.model_validate(payload).persisted_domains == []
    del payload["name"]
    with pytest.raises(ValidationError, match="name"):
        models.ProfileResponse.model_validate(payload)


def test_action_discriminator_parses_generated_action() -> None:
    result = models.ApiExecutionResponse.model_validate(
        {
            "started_at": "2026-01-01T00:00:00Z",
            "ended_at": "2026-01-01T00:00:01Z",
            "action": {"type": "goto", "url": "https://example.com"},
            "success": True,
            "message": "ok",
        }
    )
    assert isinstance(result.action, models.GotoAction)
    assert result.action.url == "https://example.com"
    assert result.model_dump(mode="json")["action"]["type"] == "goto"


def test_function_aliases_are_not_mistaken_for_core_alias_choices() -> None:
    fields = models.FunctionResponse.model_fields
    assert "workflow_id" in fields and "function_id" in fields
    assert fields["workflow_id"].is_required() and fields["function_id"].is_required()
    assert core.GetFunctionResponse.model_fields["function_id"].validation_alias is not None


def test_inline_enums_are_literals_and_named_enums_keep_string_behavior() -> None:
    from enum import StrEnum
    from typing import Literal, get_origin

    from pydantic import TypeAdapter

    for model, field, value in [
        (models.SessionResponse, "status", "closed"),
        (models.SessionResponse, "browser_type", "chromium"),
        (models.DeleteVaultResponse, "status", "success"),
        (models.GetFunctionRunResponse, "status", "closed"),
        (models.Cookie, "sameSite", "Lax"),
    ]:
        annotation = model.model_fields[field].annotation
        assert annotation is not None
        assert TypeAdapter(annotation).validate_python(value) == value
        # Nullable fields contain a Literal inside a union.
        assert "Literal" in str(annotation) or get_origin(annotation) is Literal
    for enum, value in [(models.ProxyGeolocationCountry, "fr"), (models.FileSource, "user_upload")]:
        member = enum(value)
        assert isinstance(member, StrEnum)
        assert isinstance(member, str)
        assert member == value
        assert member.value == value
