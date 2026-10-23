import asyncio
import time
from typing import TYPE_CHECKING, Literal, final

from notte_core.types import ManagedAuthOperation, ManagedAuthRunResponse

from notte_sdk._requests import wire_request
from notte_sdk.endpoints.base import AsyncBaseClient, BaseClient, NotteEndpoint

if TYPE_CHECKING:
    from notte_sdk.client import AsyncNotteClient, NotteClient


# Legacy: all four managed-auth routes are absent from the committed OpenAPI schema.
def _check_endpoint(connection_id: str) -> NotteEndpoint[ManagedAuthRunResponse]:
    return NotteEndpoint(
        path=f"connections/{connection_id}/check",
        response=ManagedAuthRunResponse,
        request=wire_request(None, {}),
        method="POST",
    )


def _operation_endpoint(operation_id: str) -> NotteEndpoint[ManagedAuthOperation]:
    return NotteEndpoint(path=f"operations/{operation_id}", response=ManagedAuthOperation, method="GET")


def _start_endpoint(
    connection_id: str, action: Literal["refresh", "reauthenticate"], auth_retry: int
) -> NotteEndpoint[ManagedAuthOperation]:
    return NotteEndpoint(
        path=f"connections/{connection_id}/{action}",
        response=ManagedAuthOperation,
        request=wire_request(None, {"auth_retry": auth_retry} if auth_retry != 0 else {}),
        method="POST",
    )


def _running(operation: ManagedAuthOperation, deadline: float) -> bool:
    """Whether `wait_for_auth` polls `operation` again; raises once `deadline` has passed."""
    if operation.status not in ("pending", "running"):
        return False
    if time.monotonic() >= deadline:
        raise TimeoutError("Timed out waiting for connection authentication")
    return True


def _succeeded(operation: ManagedAuthOperation) -> ManagedAuthOperation:
    if operation.status != "succeeded":
        raise RuntimeError(operation.error or "Connection authentication failed")
    return operation


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
        return self.request(_check_endpoint(connection_id))

    def get_operation(self, operation_id: str) -> ManagedAuthOperation:
        return self.request(_operation_endpoint(operation_id), timeout=10)

    def wait_for_auth(self, operation: ManagedAuthOperation, timeout: float = 615) -> ManagedAuthOperation:
        deadline = time.monotonic() + timeout
        while _running(operation, deadline):
            time.sleep(1)
            operation = self.get_operation(operation.id)
        return _succeeded(operation)

    def refresh_connection(self, connection_id: str, *, wait: bool = True, auth_retry: int = 0) -> ManagedAuthOperation:
        result = self.request(_start_endpoint(connection_id, "refresh", auth_retry))
        return self.wait_for_auth(result) if wait else result

    def reauthenticate_connection(
        self, connection_id: str, *, wait: bool = True, auth_retry: int = 0
    ) -> ManagedAuthOperation:
        result = self.request(_start_endpoint(connection_id, "reauthenticate", auth_retry))
        return self.wait_for_auth(result) if wait else result


@final
class AsyncManagedAuthClient(AsyncBaseClient):
    """`ManagedAuthClient` for `AsyncNotteClient`: the same methods, as coroutines."""

    def __init__(
        self,
        root_client: "AsyncNotteClient",
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

    async def check_connection(self, connection_id: str) -> ManagedAuthRunResponse:
        return await self.request(_check_endpoint(connection_id))

    async def get_operation(self, operation_id: str) -> ManagedAuthOperation:
        return await self.request(_operation_endpoint(operation_id), timeout=10)

    async def wait_for_auth(self, operation: ManagedAuthOperation, timeout: float = 615) -> ManagedAuthOperation:
        deadline = time.monotonic() + timeout
        while _running(operation, deadline):
            await asyncio.sleep(1)
            operation = await self.get_operation(operation.id)
        return _succeeded(operation)

    async def refresh_connection(
        self, connection_id: str, *, wait: bool = True, auth_retry: int = 0
    ) -> ManagedAuthOperation:
        result = await self.request(_start_endpoint(connection_id, "refresh", auth_retry))
        return await self.wait_for_auth(result) if wait else result

    async def reauthenticate_connection(
        self, connection_id: str, *, wait: bool = True, auth_retry: int = 0
    ) -> ManagedAuthOperation:
        result = await self.request(_start_endpoint(connection_id, "reauthenticate", auth_retry))
        return await self.wait_for_auth(result) if wait else result
