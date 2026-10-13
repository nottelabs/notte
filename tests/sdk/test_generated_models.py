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
            "ProfileCreateRequest",
            "ProfileCreateRequestDict",
            "ProfileListRequest",
            "ProfileListRequestDict",
            "ProfileResponse",
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
