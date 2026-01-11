"""Profiles endpoint client for the Notte SDK."""

from collections.abc import Sequence
from typing import TYPE_CHECKING, Unpack

from notte_core.common.telemetry import track_usage
from typing_extensions import final

from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from notte_sdk.types import (
    ExecutionResponse,
    ProfileCreateRequest,
    ProfileCreateRequestDict,
    ProfileListRequest,
    ProfileListRequestDict,
    ProfileResponse,
)

if TYPE_CHECKING:
    from notte_sdk.client import NotteClient


@final
class ProfilesClient(BaseClient):
    """Client for managing browser profiles."""

    # Profile endpoints
    CREATE_PROFILE = "create"
    GET_PROFILE = "{profile_id}"
    DELETE_PROFILE = "{profile_id}"
    LIST_PROFILES = ""

    def __init__(
        self,
        root_client: "NotteClient",
        api_key: str | None = None,
        server_url: str | None = None,
        verbose: bool = False,
    ):
        """Initialize ProfilesClient.

        Args:
            root_client: Root NotteClient instance
            api_key: Optional API key for authentication
            server_url: Optional server URL override
            verbose: Whether to enable verbose logging
        """
        super().__init__(
            root_client=root_client,
            base_endpoint_path="profiles",
            server_url=server_url,
            api_key=api_key,
            verbose=verbose,
        )

    @staticmethod
    def _create_profile_endpoint() -> NotteEndpoint[ProfileResponse]:
        """Returns a NotteEndpoint configured for creating a profile."""
        return NotteEndpoint(
            path=ProfilesClient.CREATE_PROFILE,
            response=ProfileResponse,
            method="POST",
        )

    @staticmethod
    def _get_profile_endpoint(profile_id: str) -> NotteEndpoint[ProfileResponse]:
        """Returns a NotteEndpoint configured for getting a profile."""
        return NotteEndpoint(
            path=ProfilesClient.GET_PROFILE.format(profile_id=profile_id),
            response=ProfileResponse,
            method="GET",
        )

    @staticmethod
    def _delete_profile_endpoint(profile_id: str) -> NotteEndpoint[ExecutionResponse]:
        """Returns a NotteEndpoint configured for deleting a profile."""
        return NotteEndpoint(
            path=ProfilesClient.DELETE_PROFILE.format(profile_id=profile_id),
            response=ExecutionResponse,
            method="DELETE",
        )

    @staticmethod
    def _list_profiles_endpoint() -> NotteEndpoint[ProfileResponse]:
        """Returns a NotteEndpoint configured for listing profiles."""
        return NotteEndpoint(
            path=ProfilesClient.LIST_PROFILES,
            response=ProfileResponse,
            method="GET",
        )

    @track_usage("cloud.profile.create")
    def create(self, **data: Unpack[ProfileCreateRequestDict]) -> ProfileResponse:
        """Create a new browser profile.

        Args:
            **data: Profile creation parameters (name is optional)

        Returns:
            ProfileResponse: Created profile with ID and metadata

        Example:
            ```python
            profile = client.profiles.create(name="my-profile")
            print(profile.profile_id)  # notte-profile-a1b2c3d4e5f6g7h8
            ```
        """
        request = ProfileCreateRequest.model_validate(data)
        return self.request(ProfilesClient._create_profile_endpoint().with_request(request))

    @track_usage("cloud.profile.get")
    def get(self, profile_id: str) -> ProfileResponse:
        """Get a profile by ID.

        Args:
            profile_id: Profile ID to retrieve

        Returns:
            ProfileResponse: Profile metadata

        Raises:
            NotteAPIError: If profile not found (404) or access denied
        """
        return self.request(ProfilesClient._get_profile_endpoint(profile_id))

    @track_usage("cloud.profile.delete")
    def delete(self, profile_id: str) -> bool:
        """Delete a profile.

        Args:
            profile_id: Profile ID to delete

        Returns:
            bool: True if deleted successfully

        Raises:
            NotteAPIError: If profile not found (404) or access denied
        """
        result = self.request(ProfilesClient._delete_profile_endpoint(profile_id))
        return result.success

    @track_usage("cloud.profile.list")
    def list(self, **data: Unpack[ProfileListRequestDict]) -> Sequence[ProfileResponse]:
        """List all profiles for the authenticated user.

        Args:
            **data: List parameters (page, page_size, name filter)

        Returns:
            Sequence[ProfileResponse]: List of profiles

        Example:
            ```python
            profiles = client.profiles.list(page=1, page_size=10)
            for profile in profiles:
                print(profile.name)
            ```
        """
        params = ProfileListRequest.model_validate(data)
        endpoint = ProfilesClient._list_profiles_endpoint().with_params(params)
        return self.request_list(endpoint)
