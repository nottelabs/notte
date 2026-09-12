import time
from typing import TYPE_CHECKING, final

from pydantic import Field

from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from notte_sdk.types import ManagedAuthOperation, ManagedAuthRunResponse, SdkRequest

if TYPE_CHECKING:
    from notte_sdk.client import NotteClient


class _AuthRequest(SdkRequest):
    auth_retry: int = Field(default=0, ge=0, le=2)


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

    def get_operation(self, operation_id: str) -> ManagedAuthOperation:
        return self.request(
            NotteEndpoint(path=f"operations/{operation_id}", response=ManagedAuthOperation, method="GET"), timeout=10
        )

    def wait_for_auth(self, operation: ManagedAuthOperation, timeout: float = 615) -> ManagedAuthOperation:
        deadline = time.monotonic() + timeout
        while operation.status in ("pending", "running"):
            if time.monotonic() >= deadline:
                raise TimeoutError("Timed out waiting for connection authentication")
            time.sleep(1)
            operation = self.get_operation(operation.id)
        if operation.status != "succeeded":
            raise RuntimeError(operation.error or "Connection authentication failed")
        return operation

    def refresh_connection(self, connection_id: str, *, wait: bool = True, auth_retry: int = 0) -> ManagedAuthOperation:
        result = self.request(
            NotteEndpoint(
                path=f"connections/{connection_id}/refresh",
                response=ManagedAuthOperation,
                request=_AuthRequest(auth_retry=auth_retry),
                method="POST",
            )
        )
        return self.wait_for_auth(result) if wait else result

    def reauthenticate_connection(
        self, connection_id: str, *, wait: bool = True, auth_retry: int = 0
    ) -> ManagedAuthOperation:
        result = self.request(
            NotteEndpoint(
                path=f"connections/{connection_id}/reauthenticate",
                response=ManagedAuthOperation,
                request=_AuthRequest(auth_retry=auth_retry),
                method="POST",
            )
        )
        return self.wait_for_auth(result) if wait else result
