"""A client's resources expose one execution mode, including inherited operations."""

import inspect

import pytest
from notte_sdk import AsyncNotteClient, NotteClient
from notte_sdk.endpoints.files import AsyncRemoteFileStorage, RemoteFileStorage
from notte_sdk.endpoints.functions import AsyncNotteFunction, NotteFunction
from notte_sdk.endpoints.personas import AsyncNottePersona, NottePersona
from notte_sdk.endpoints.sessions import AsyncRemoteSession, RemoteSession
from notte_sdk.endpoints.vaults import AsyncNotteVault, NotteVault


@pytest.mark.parametrize(
    "resource", [NotteClient, RemoteSession, NotteVault, NottePersona, RemoteFileStorage, NotteFunction]
)
def test_sync_resources_have_no_public_coroutines(resource: type) -> None:
    for name in dir(resource):
        if not name.startswith("_"):
            member = inspect.getattr_static(resource, name)
            function = member.fget if isinstance(member, property) else member
            assert not inspect.iscoroutinefunction(inspect.unwrap(function)), name
    assert not hasattr(resource, "__aenter__")
    assert not hasattr(resource, "__aexit__")
    assert not hasattr(resource, "__await__")


@pytest.mark.parametrize(
    "resource",
    [
        AsyncNotteClient,
        AsyncRemoteSession,
        AsyncNotteVault,
        AsyncNottePersona,
        AsyncRemoteFileStorage,
        AsyncNotteFunction,
    ],
)
def test_async_resources_have_no_sync_context_manager(resource: type) -> None:
    assert not hasattr(resource, "__enter__")
    assert not hasattr(resource, "__exit__")


@pytest.mark.asyncio
async def test_sync_session_rejects_async_with_before_creating_a_browser() -> None:
    with NotteClient(api_key="test-api-key") as client:  # pragma: allowlist secret
        with pytest.raises(TypeError, match="asynchronous context manager"):
            async with client.Session():
                pytest.fail("sync sessions must reject async context management")
