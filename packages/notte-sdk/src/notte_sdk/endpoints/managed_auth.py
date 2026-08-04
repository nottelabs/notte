from typing import TYPE_CHECKING, final

from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from notte_sdk.types import ManagedAuthRunResponse, SdkRequest

if TYPE_CHECKING:
    from notte_sdk.client import NotteClient


class _EmptyRequest(SdkRequest):
    """Empty JSON body required by the SDK's POST transport."""


@final
class ManagedAuthClient(BaseClient):
    def __init__(
        self,
        root_client: "NotteClient",
        api_key: str | None = None,
        server_url: str | None = None,
        verbose: bool = False,
    ) -> None:
        super().__init__(
            root_client=root_client,
            base_endpoint_path="managed-auth",
            api_key=api_key,
            server_url=server_url,
            verbose=verbose,
        )

    def check_connection(self, connection_id: str) -> ManagedAuthRunResponse:
        endpoint = NotteEndpoint(
            path=f"connections/{connection_id}/check",
            response=ManagedAuthRunResponse,
            request=_EmptyRequest(),
            method="POST",
        )
        return self.request(endpoint)
