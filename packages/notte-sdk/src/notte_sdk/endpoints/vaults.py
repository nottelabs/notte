from __future__ import annotations

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

from notte_sdk._generated.resources import VaultsOperations
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
            logger.warning(
                f"[Vault] {response.vault_id} created since no vault id was provided. Please store this to retrieve it later."
            )
            self.vault_id = response.vault_id
        else:
            self.vault_id = _client.get(vault_id)

    @override
    def start(self) -> None:
        pass

    @override
    def stop(self) -> None:
        logger.info(f"[Vault] {self.vault_id} deleted. All credentials have been deleted.")
        self.delete()

    @override
    @profiler.profiled(operation_name="BaseVault.add_credentials_async")
    async def add_credentials_async(self, url: str, **kwargs: Unpack[CredentialsDict]) -> None:
        """Store credentials remotely; invalid input is reported by the API as 422."""
        return await self._add_credentials(url, kwargs)

    @override
    async def _add_credentials(self, url: str, creds: CredentialsDict) -> None:
        _ = self.vault_client.credentials_add(self.vault_id, url=url, **creds)

    @override
    async def _get_credentials_impl(self, url: str) -> CredentialsDict | None:
        return self.vault_client.credentials_get(vault_id=self.vault_id, url=url).credentials

    @override
    async def delete_credentials_async(self, url: str) -> None:
        _ = self.vault_client.credentials_delete(vault_id=self.vault_id, url=url)

    @override
    async def set_credit_card_async(self, **kwargs: Unpack[CreditCardDict]) -> None:
        _ = self.vault_client.credit_card_set(self.vault_id, **kwargs)

    @override
    async def get_credit_card_async(self) -> CreditCardDict:
        return self.vault_client.credit_card_get(self.vault_id).credit_card

    @override
    async def list_credentials_async(self) -> list[Credential]:
        return self.vault_client.credentials_list(self.vault_id).credentials

    @override
    async def delete_credit_card_async(self) -> None:
        _ = self.vault_client.credit_card_delete(self.vault_id)

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
        if len(vault_id) == 0:
            raise ValueError("Vault ID cannot be empty")
        _ = self.credentials_list(vault_id)
        return vault_id
