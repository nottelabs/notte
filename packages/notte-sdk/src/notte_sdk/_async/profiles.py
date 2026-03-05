"""Async profiles endpoint client for the Notte SDK."""
# pyright: reportImportCycles=false

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Unpack

from notte_core.common.telemetry import track_usage
from typing_extensions import final

from notte_sdk._async.base import AsyncBaseClient, NotteEndpoint
from notte_sdk._async.http import AsyncHTTPClient
from notte_sdk.types import (
    ExecutionResponse,
    ProfileCreateRequest,
    ProfileCreateRequestDict,
    ProfileListRequest,
    ProfileListRequestDict,
    ProfileResponse,
)

if TYPE_CHECKING:
    from notte_sdk._async.client import AsyncNotteClient


@final
class AsyncProfilesClient(AsyncBaseClient):
    """Async client for managing browser profiles."""

    # Profile endpoints
    CREATE_PROFILE = "create"
    GET_PROFILE = "{profile_id}"
    DELETE_PROFILE = "{profile_id}"
    LIST_PROFILES = ""

    def __init__(
        self,
        root_client: "AsyncNotteClient",
        http_client: AsyncHTTPClient,
        server_url: str,
        api_key: str,
        verbose: bool = False,
    ):
        """Initialize AsyncProfilesClient.

        Args:
            root_client: Root AsyncNotteClient instance.
            http_client: Shared AsyncHTTPClient instance.
            server_url: API server URL.
            api_key: API key for authentication.
            verbose: Whether to enable verbose logging.
        """
        super().__init__(
            root_client=root_client,
            base_endpoint_path="profiles",
            http_client=http_client,
            server_url=server_url,
            api_key=api_key,
            verbose=verbose,
        )

    @staticmethod
    def _create_profile_endpoint() -> NotteEndpoint[ProfileResponse]:
        """Returns a NotteEndpoint configured for creating a profile."""
        return NotteEndpoint(
            path=AsyncProfilesClient.CREATE_PROFILE,
            response=ProfileResponse,
            method="POST",
        )

    @staticmethod
    def _get_profile_endpoint(profile_id: str) -> NotteEndpoint[ProfileResponse]:
        """Returns a NotteEndpoint configured for getting a profile."""
        return NotteEndpoint(
            path=AsyncProfilesClient.GET_PROFILE.format(profile_id=profile_id),
            response=ProfileResponse,
            method="GET",
        )

    @staticmethod
    def _delete_profile_endpoint(profile_id: str) -> NotteEndpoint[ExecutionResponse]:
        """Returns a NotteEndpoint configured for deleting a profile."""
        return NotteEndpoint(
            path=AsyncProfilesClient.DELETE_PROFILE.format(profile_id=profile_id),
            response=ExecutionResponse,
            method="DELETE",
        )

    @staticmethod
    def _list_profiles_endpoint() -> NotteEndpoint[ProfileResponse]:
        """Returns a NotteEndpoint configured for listing profiles."""
        return NotteEndpoint(
            path=AsyncProfilesClient.LIST_PROFILES,
            response=ProfileResponse,
            method="GET",
        )

    @track_usage("cloud.profile.create")
    async def create(self, **data: Unpack[ProfileCreateRequestDict]) -> ProfileResponse:
        """Create a new browser profile.

        Args:
            **data: Profile creation parameters (name is optional).

        Returns:
            ProfileResponse: Created profile with ID and metadata.
        """
        request = ProfileCreateRequest.model_validate(data)
        return await self.request(AsyncProfilesClient._create_profile_endpoint().with_request(request))

    @track_usage("cloud.profile.get")
    async def get(self, profile_id: str) -> ProfileResponse:
        """Get a profile by ID.

        Args:
            profile_id: Profile ID to retrieve.

        Returns:
            ProfileResponse: Profile metadata.
        """
        return await self.request(AsyncProfilesClient._get_profile_endpoint(profile_id))

    @track_usage("cloud.profile.delete")
    async def delete(self, profile_id: str) -> bool:
        """Delete a profile.

        Args:
            profile_id: Profile ID to delete.

        Returns:
            bool: True if deleted successfully.
        """
        result = await self.request(AsyncProfilesClient._delete_profile_endpoint(profile_id))
        return result.success

    @track_usage("cloud.profile.list")
    async def list(self, **data: Unpack[ProfileListRequestDict]) -> Sequence[ProfileResponse]:
        """List all profiles for the authenticated user.

        Args:
            **data: List parameters (page, page_size, name filter).

        Returns:
            Sequence[ProfileResponse]: List of profiles.
        """
        params = ProfileListRequest.model_validate(data)
        endpoint = AsyncProfilesClient._list_profiles_endpoint().with_params(params)
        return await self.request_list(endpoint)
