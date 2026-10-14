"""Profiles parity overrides; see docs/design/sdk-codegen.md for the manifest."""

from pydantic import Field

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

    page_size: int = 20
    only_active: bool = Field(default=True, exclude=True)
    only_current_token: bool = Field(default=False, exclude=True)
