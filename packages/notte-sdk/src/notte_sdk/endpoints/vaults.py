from __future__ import annotations

import asyncio
import secrets
from typing import Unpack, final, overload

from notte_core.credentials.base import (
    BaseVault,
    Credential,
    CredentialsDict,
    CreditCardDict,
)
from notte_core.logging import logger
from notte_core.profiling import profiler
from notte_core.resource import SyncResource
from typing_extensions import override

from notte_sdk._generated.resources import AsyncVaultsOperations, VaultsOperations
from notte_sdk._transport import athread_finally
from notte_sdk.endpoints._async_resource import AwaitableResource
from notte_sdk.types import (
    VaultCreateRequestDict,
)


# DEFINED HERE TO SIMPLIFY CIRCULAR DEPENDENCY
# SHOULD ONLY BE INVOKED FROM ENDPOINT ANYWAY
@final
class NotteVault(BaseVault, SyncResource):
    """Vault that fetches credentials stored using the sdk"""

    @overload
    def __init__(self, /, vault_id: str, *, _client: VaultsClient | None = None) -> None: ...

    @overload
    def __init__(self, *, _client: VaultsClient | None = None, **data: Unpack[VaultCreateRequestDict]) -> None: ...

    def __init__(
        self,
        vault_id: str | None = None,
        *,
        _client: VaultsClient | None = None,
        **data: Unpack[VaultCreateRequestDict],
    ) -> None:
        if _client is None:
            raise ValueError("VaultsClient is required")
        super().__init__()

        self.vault_client = _client
        if vault_id is None:
            # create a new vault
            response = _client.create(**data)
            _log_created(response.vault_id)
            self.vault_id = response.vault_id
        else:
            self.vault_id = _client.get(vault_id)

    @override
    def start(self) -> None:
        pass

    @override
    def stop(self) -> None:
        _log_deleted(self.vault_id)
        self.delete()

    @override
    @profiler.profiled(operation_name="BaseVault.add_credentials_async")
    async def add_credentials_async(self, url: str, **kwargs: Unpack[CredentialsDict]) -> None:
        """Store credentials remotely; invalid input is reported by the API as 422."""
        return await self._add_credentials(url, kwargs)

    @override
    async def _add_credentials(self, url: str, creds: CredentialsDict) -> None:
        _ = await asyncio.to_thread(self.vault_client.credentials_add, self.vault_id, url=url, **creds)

    @override
    async def _get_credentials_impl(self, url: str) -> CredentialsDict | None:
        return (await asyncio.to_thread(self.vault_client.credentials_get, vault_id=self.vault_id, url=url)).credentials

    @override
    async def delete_credentials_async(self, url: str) -> None:
        await athread_finally(self.vault_client.credentials_delete, vault_id=self.vault_id, url=url)

    @override
    async def set_credit_card_async(self, **kwargs: Unpack[CreditCardDict]) -> None:
        _ = await asyncio.to_thread(self.vault_client.credit_card_set, self.vault_id, **kwargs)

    @override
    async def get_credit_card_async(self) -> CreditCardDict:
        return (await asyncio.to_thread(self.vault_client.credit_card_get, self.vault_id)).credit_card

    @override
    async def list_credentials_async(self) -> list[Credential]:
        return (await asyncio.to_thread(self.vault_client.credentials_list, self.vault_id)).credentials

    @override
    async def delete_credit_card_async(self) -> None:
        await athread_finally(self.vault_client.credit_card_delete, self.vault_id)

    def delete(self) -> None:
        _ = self.vault_client.delete(self.vault_id)

    def generate_password(self, length: int = 20, include_special_chars: bool = True) -> str:
        """Generate a secure random password.

        Args:
            length: The desired length of the password (default: 20)
            include_special_chars: Whether to include special characters (default: True)

        Returns:
            A secure random password string

        Raises:
            ValueError: If length is too short to meet security requirements
        """
        return _generate_password(length, include_special_chars)


def _log_created(vault_id: str) -> None:
    logger.warning(
        f"[Vault] {vault_id} created since no vault id was provided. Please store this to retrieve it later."
    )


def _log_deleted(vault_id: str) -> None:
    logger.info(f"[Vault] {vault_id} deleted. All credentials have been deleted.")


def _check_vault_id(vault_id: str) -> None:
    if len(vault_id) == 0:
        raise ValueError("Vault ID cannot be empty")


def _generate_password(length: int, include_special_chars: bool) -> str:
    """`generate_password` of `NotteVault` and `AsyncNotteVault`."""
    # Validate minimum length
    min_required_length = 4 if include_special_chars else 3
    if length < min_required_length:
        msg = f"Password length must be at least {min_required_length} characters"
        raise ValueError(msg)

    # Use token_urlsafe for speed, then replace characters to meet requirements
    # This is much faster than character-by-character generation
    password = secrets.token_urlsafe(length)[:length]

    # Ensure we have the required character types by replacing some characters
    # This maintains randomness while guaranteeing complexity requirements
    password_list = list(password)

    # Guarantee at least one lowercase (replace first char if needed)
    if not any(c.islower() for c in password_list):
        password_list[0] = secrets.choice("abcdefghijklmnopqrstuvwxyz")

    # Guarantee at least one uppercase (replace second char if needed)
    if not any(c.isupper() for c in password_list):
        idx = 1 if length > 1 else 0
        password_list[idx] = secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

    # Guarantee at least one digit (replace third char if needed)
    if not any(c.isdigit() for c in password_list):
        idx = 2 if length > 2 else 0
        password_list[idx] = secrets.choice("0123456789")

    # Guarantee at least one special char if required (replace fourth char if needed)
    if include_special_chars and not any(c in "!@#$%^&*()_+-=[]|;:,.<>?" for c in password_list):
        idx = 3 if length > 3 else 0
        password_list[idx] = secrets.choice("!@#$%^&*()_+-=[]|;:,.<>?")

    return "".join(password_list)


@final
class VaultsClient(VaultsOperations):
    """
    Client for the Notte API.

    Note: this client is only able to handle one session at a time.
    If you need to handle multiple sessions, you need to create a new client for each session.
    """

    def get(self, vault_id: str) -> str:
        _check_vault_id(vault_id)
        _ = self.credentials_list(vault_id)
        return vault_id


@final
class AsyncNotteVault(BaseVault, AwaitableResource):
    """`NotteVault` for `AsyncNotteClient`: the same methods, as coroutines.

    ```python
    async with client.Vault() as vault:
        await vault.add_credentials("https://github.com", email="me@example.com", password="...")
    ```

    `vault = await client.Vault(...)` creates the vault, or checks that `vault_id` exists, like the
    `NotteVault` constructor; `async with` also deletes it on exit. Credentials go through the same
    `BaseVault` code as `NotteVault`, so the values it returns are tracked and masked the same way.
    """

    @overload
    def __init__(self, /, vault_id: str, *, _client: AsyncVaultsClient | None = None) -> None: ...

    @overload
    def __init__(self, *, _client: AsyncVaultsClient | None = None, **data: Unpack[VaultCreateRequestDict]) -> None: ...

    def __init__(
        self,
        vault_id: str | None = None,
        *,
        _client: AsyncVaultsClient | None = None,
        **data: Unpack[VaultCreateRequestDict],
    ) -> None:
        if _client is None:
            raise ValueError("AsyncVaultsClient is required")
        super().__init__()

        self.vault_client: AsyncVaultsClient = _client
        self._vault_id: str | None = vault_id
        self._create_request: VaultCreateRequestDict = data
        self._ready: bool = False

    @property
    def vault_id(self) -> str:
        if self._vault_id is None:
            raise ValueError("Vault not created yet: `await` it or use `async with` first")
        return self._vault_id

    @override
    async def _start(self) -> None:
        """Create the vault, or check that `vault_id` exists, unless that was already done."""
        if self._ready:
            return
        if self._vault_id is None:
            # create a new vault
            response = await self.vault_client.create(**self._create_request)
            _log_created(response.vault_id)
            self._vault_id = response.vault_id
        else:
            self._vault_id = await self.vault_client.get(self._vault_id)
        self._ready = True

    @override
    async def stop(self) -> None:
        _log_deleted(self.vault_id)
        await self.delete()

    @override
    @profiler.profiled(operation_name="BaseVault.add_credentials_async")
    async def add_credentials_async(self, url: str, **kwargs: Unpack[CredentialsDict]) -> None:
        """Store credentials remotely; invalid input is reported by the API as 422."""
        return await self._add_credentials(url, kwargs)

    @override
    async def _add_credentials(self, url: str, creds: CredentialsDict) -> None:
        _ = await self.vault_client.credentials_add(self.vault_id, url=url, **creds)

    @override
    async def _get_credentials_impl(self, url: str) -> CredentialsDict | None:
        return (await self.vault_client.credentials_get(vault_id=self.vault_id, url=url)).credentials

    @override
    async def delete_credentials_async(self, url: str) -> None:
        _ = await self.vault_client.credentials_delete(vault_id=self.vault_id, url=url)

    @override
    async def set_credit_card_async(self, **kwargs: Unpack[CreditCardDict]) -> None:
        _ = await self.vault_client.credit_card_set(self.vault_id, **kwargs)

    @override
    async def get_credit_card_async(self) -> CreditCardDict:
        return (await self.vault_client.credit_card_get(self.vault_id)).credit_card

    @override
    async def list_credentials_async(self) -> list[Credential]:
        return (await self.vault_client.credentials_list(self.vault_id)).credentials

    @override
    async def delete_credit_card_async(self) -> None:
        _ = await self.vault_client.credit_card_delete(self.vault_id)

    # The sync `BaseVault` methods, as coroutines: each awaits its `*_async` method, as `BaseVault` runs it.

    @override
    async def add_credentials(self, url: str, **kwargs: Unpack[CredentialsDict]) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        return await self.add_credentials_async(url, **kwargs)

    @override
    async def set_credit_card(self, **kwargs: Unpack[CreditCardDict]) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        return await self.set_credit_card_async(**kwargs)

    @override
    async def get_credit_card(self) -> CreditCardDict:  # pyright: ignore[reportIncompatibleMethodOverride]
        return await self.get_credit_card_async()

    @override
    async def delete_credit_card(self) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        return await self.delete_credit_card_async()

    @override
    async def delete_credentials(self, url: str) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        return await self.delete_credentials_async(url=url)

    @override
    async def list_credentials(self) -> list[Credential]:  # pyright: ignore[reportIncompatibleMethodOverride]
        return await self.list_credentials_async()

    @override
    async def has_credential(self, url: str) -> bool:  # pyright: ignore[reportIncompatibleMethodOverride]
        return await self.has_credential_async(url=url)

    @override
    async def add_credentials_from_env(self, url: str) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        return await self.add_credentials_from_env_async(url=url)

    @override
    async def get_credentials(self, url: str) -> CredentialsDict | None:  # pyright: ignore[reportIncompatibleMethodOverride]
        return await self.get_credentials_async(url=url)

    async def delete(self) -> None:
        _ = await self.vault_client.delete(self.vault_id)

    def generate_password(self, length: int = 20, include_special_chars: bool = True) -> str:
        """Generate a secure random password.

        Args:
            length: The desired length of the password (default: 20)
            include_special_chars: Whether to include special characters (default: True)

        Returns:
            A secure random password string

        Raises:
            ValueError: If length is too short to meet security requirements
        """
        return _generate_password(length, include_special_chars)


@final
class AsyncVaultsClient(AsyncVaultsOperations):
    """`VaultsClient` for `AsyncNotteClient`."""

    async def get(self, vault_id: str) -> str:
        _check_vault_id(vault_id)
        _ = await self.credentials_list(vault_id)
        return vault_id
