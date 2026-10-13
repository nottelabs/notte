"""Profiles endpoint client for the Notte SDK."""

from collections.abc import Sequence
from typing import TYPE_CHECKING, Unpack

from notte_core.common.telemetry import track_usage
from typing_extensions import final

from notte_sdk._generated.resources import ProfilesOperations
from notte_sdk.types import ProfileCreateRequestDict, ProfileListRequestDict, ProfileResponse

if TYPE_CHECKING:
    from notte_sdk.client import NotteClient


@final
class ProfilesClient(ProfilesOperations):
    """Client for managing browser profiles."""

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
        return self._profile_create(**data)

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
        return self._profile_get(profile_id)

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
        return self._profile_delete(profile_id)

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
        return self._profile_list(**data)
