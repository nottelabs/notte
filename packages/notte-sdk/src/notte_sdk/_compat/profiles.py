"""Profiles parity overrides; see docs/design/sdk-codegen.md for the manifest."""

from typing import Any, ClassVar, cast

from pydantic import ConfigDict, Field, model_validator

from notte_sdk._generated import models


class ProfileResponse(models.ProfileResponse):
    """Profile metadata with the SDK's non-null, independently allocated domain list."""

    persisted_domains: list[str] = Field(default_factory=list)  # pyright: ignore[reportIncompatibleVariableOverride]


class ProfileDeleteResponse(models.ProfileDeleteResponse):
    """An empty or incomplete response must not report a successful deletion."""

    success: bool = Field(...)  # pyright: ignore[reportGeneralTypeIssues]
    message: str = Field(...)  # pyright: ignore[reportGeneralTypeIssues]


class ProfileListRequest(models.ProfileListParametersQuery):
    """Keep the existing public query defaults and leave pagination bounds to the API."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")
    page: int = 1
    page_size: int = 20
    only_active: bool = Field(default=True, exclude=True)
    only_current_token: bool = Field(default=False, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def reject_api_only_filters(cls, data: Any) -> Any:
        if isinstance(data, dict):
            values = cast(dict[str, Any], data)
            if {"only_active", "only_current_token"}.intersection(values):
                raise ValueError("only_active and only_current_token are not public SDK profile filters")
            return values
        return data
