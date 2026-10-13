from __future__ import annotations

import secrets
from collections.abc import Sequence
from typing import TYPE_CHECKING, Unpack, final, overload

from notte_core.common.logging import logger
from notte_core.common.resource import SyncResource
from notte_core.common.telemetry import track_usage
from notte_core.credentials.base import (
    BaseVault,
    Credential,
    CredentialsDict,
    CreditCardDict,
    Vault,
)
from notte_core.types import (
    AddCredentialsRequest,
    AddCredentialsRequestDict,
    AddCredentialsResponse,
    AddCreditCardRequest,
    AddCreditCardRequestDict,
    AddCreditCardResponse,
    DeleteCredentialsRequest,
    DeleteCredentialsRequestDict,
    DeleteCredentialsResponse,
    DeleteCreditCardRequest,
    DeleteCreditCardRequestDict,
    DeleteCreditCardResponse,
    DeleteVaultRequest,
    DeleteVaultRequestDict,
    DeleteVaultResponse,
    GetCredentialsRequest,
    GetCredentialsRequestDict,
    GetCredentialsResponse,
    GetCreditCardRequest,
    GetCreditCardRequestDict,
    GetCreditCardResponse,
    ListCredentialsRequest,
    ListCredentialsRequestDict,
    ListCredentialsResponse,
    VaultCreateRequest,
    VaultCreateRequestDict,
    VaultListRequest,
    VaultListRequestDict,
)
from typing_extensions import override

from notte_sdk._generated import endpoints as api
from notte_sdk.endpoints.base import BaseClient

if TYPE_CHECKING:
    from notte_sdk.client import NotteClient


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
    async def _add_credentials(self, url: str, creds: CredentialsDict) -> None:
        _ = self.vault_client.add_or_update_credentials(self.vault_id, url=url, **creds)

    @override
    async def _get_credentials_impl(self, url: str) -> CredentialsDict | None:
        return self.vault_client.get_credentials(vault_id=self.vault_id, url=url).credentials

    @override
    async def delete_credentials_async(self, url: str) -> None:
        _ = self.vault_client.delete_credentials(vault_id=self.vault_id, url=url)

    @override
    async def set_credit_card_async(self, **kwargs: Unpack[CreditCardDict]) -> None:
        _ = self.vault_client.set_credit_card(self.vault_id, **kwargs)

    @override
    async def get_credit_card_async(self) -> CreditCardDict:
        return self.vault_client.get_credit_card(self.vault_id).credit_card

    @override
    async def list_credentials_async(self) -> list[Credential]:
        return self.vault_client.list_credentials(self.vault_id).credentials

    @override
    async def delete_credit_card_async(self) -> None:
        _ = self.vault_client.delete_credit_card(self.vault_id)

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
class VaultsClient(BaseClient):
    """
    Client for the Notte API.

    Note: this client is only able to handle one session at a time.
    If you need to handle multiple sessions, you need to create a new client for each session.
    """

    def __init__(
        self,
        root_client: "NotteClient",
        api_key: str | None = None,
        server_url: str | None = None,
        verbose: bool = False,
    ):
        """
        Initialize a VaultsClient instance.

        Initializes the client with an optional API key for vault management.
        """
        super().__init__(
            root_client=root_client,
            base_endpoint_path="vaults",
            server_url=server_url,
            api_key=api_key,
            verbose=verbose,
        )

    @track_usage("cloud.vault.create")
    def create(self, **data: Unpack[VaultCreateRequestDict]) -> Vault:
        """
        Create vault

        Args:
            **data: Unpacked dictionary containing the vault creation parameters.

        Returns:
            NotteVault: The created vault
        """
        params = VaultCreateRequest.model_validate(data)
        return self.request(api.vault_create(params))

    def get(self, vault_id: str) -> str:
        if len(vault_id) == 0:
            raise ValueError("Vault ID cannot be empty")
        _ = self.list_credentials(vault_id)
        return vault_id

    @track_usage("cloud.vault.credentials.add")
    def add_or_update_credentials(
        self, vault_id: str, **data: Unpack[AddCredentialsRequestDict]
    ) -> AddCredentialsResponse:
        """
        Adds or updates credentials in a vault.

        Args:
            vault_id: ID of the vault to add or update credentials in.
            **data: Unpacked dictionary containing credential information.

        Returns:
            AddCredentialsResponse: Response from the add credentials endpoint.
        """
        params = AddCredentialsRequest.from_dict(data)
        response = self.request(api.vault_credentials_add(vault_id, params))
        return response

    @track_usage("cloud.vault.credentials.get")
    def get_credentials(self, vault_id: str, **data: Unpack[GetCredentialsRequestDict]) -> GetCredentialsResponse:
        """
        Retrieves credentials from a vault.

        Args:
            vault_id: ID of the vault containing the credentials.
            **data: Unpacked dictionary containing parameters for the request.

        Returns:
            GetCredentialsResponse: Response containing the requested credentials.
        """
        params = GetCredentialsRequest.model_validate(data)
        response = self.request(api.vault_credentials_get(vault_id, params=params))
        return response

    @track_usage("cloud.vault.credentials.delete")
    def delete_credentials(
        self, vault_id: str, **data: Unpack[DeleteCredentialsRequestDict]
    ) -> DeleteCredentialsResponse:
        """
        Deletes credentials from a vault.

        Args:
            vault_id: ID of the vault containing the credentials to delete.
            **data: Unpacked dictionary containing parameters specifying the credentials to delete.

        Returns:
            DeleteCredentialsResponse: Response from the delete credentials endpoint.
        """
        params = DeleteCredentialsRequest.model_validate(data)
        response = self.request(api.vault_credentials_delete(vault_id, params=params))
        return response

    @track_usage("cloud.vault.delete")
    def delete(self, vault_id: str, **data: Unpack[DeleteVaultRequestDict]) -> DeleteVaultResponse:
        """
        Deletes a vault.

        Args:
            vault_id: ID of the vault to delete.
            **data: Unpacked dictionary containing parameters for the request.

        Returns:
            DeleteVaultResponse: Response from the delete vault endpoint.
        """
        _ = DeleteVaultRequest.model_validate(data)  # no parameters: rejects unknown keywords
        response = self.request(api.vault_delete(vault_id))
        return response

    @track_usage("cloud.vault.credentials.list")
    def list_credentials(self, vault_id: str, **data: Unpack[ListCredentialsRequestDict]) -> ListCredentialsResponse:
        """
        Lists credentials in a vault.

        Args:
            vault_id: ID of the vault to list credentials from.
            **data: Unpacked dictionary containing parameters for the request.

        Returns:
            ListCredentialsResponse: Response containing the list of credentials.
        """
        _ = ListCredentialsRequest.model_validate(data)  # no parameters: rejects unknown keywords
        response = self.request(api.vault_credentials_list(vault_id))
        return response

    @track_usage("cloud.vault.list")
    def list(self, **data: Unpack[VaultListRequestDict]) -> Sequence[Vault]:
        """
        Lists all available vaults.

        Args:
            **data: Unpacked dictionary containing parameters for the request.

        Returns:
            ListVaultsResponse: Response containing the list of vaults.
        """
        params = VaultListRequest.model_validate(data)
        return self.request_list(api.list_vaults(params=params))

    @track_usage("cloud.vault.credit_card.delete")
    def delete_credit_card(
        self, vault_id: str, **data: Unpack[DeleteCreditCardRequestDict]
    ) -> DeleteCreditCardResponse:
        """
        Deletes a credit card from a vault.

        Args:
            vault_id: ID of the vault containing the credit card to delete.
            **data: Unpacked dictionary containing parameters specifying the credit card to delete.

        Returns:
            DeleteCreditCardResponse: Response from the delete credit card endpoint.
        """
        _ = DeleteCreditCardRequest.model_validate(data)  # no parameters: rejects unknown keywords
        response = self.request(api.vault_credit_card_delete(vault_id))
        return response

    @track_usage("cloud.vault.credit_card.get")
    def get_credit_card(self, vault_id: str, **data: Unpack[GetCreditCardRequestDict]) -> GetCreditCardResponse:
        """
        Retrieves a credit card from a vault.

        Args:
            vault_id: ID of the vault containing the credit card.
            **data: Unpacked dictionary containing parameters for the request.

        Returns:
            GetCreditCardResponse: Response containing the requested credit card information.
        """
        _ = GetCreditCardRequest.model_validate(data)  # no parameters: rejects unknown keywords
        response = self.request(api.vault_credit_card_get(vault_id))
        return response

    @track_usage("cloud.vault.credit_card.set")
    def set_credit_card(self, vault_id: str, **data: Unpack[AddCreditCardRequestDict]) -> AddCreditCardResponse:
        """
        Sets a credit card in a vault.

        Args:
            vault_id: ID of the vault to add the credit card to.
            **data: Unpacked dictionary containing credit card information.

        Returns:
            AddCreditCardResponse: Response from the add credit card endpoint.
        """
        params = AddCreditCardRequest.from_dict(data)
        response = self.request(api.vault_credit_card_set(vault_id, params))
        return response
