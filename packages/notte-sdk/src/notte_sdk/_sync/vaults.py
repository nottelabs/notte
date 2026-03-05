"""Async vaults endpoint client for the Notte SDK."""
# Auto-generated from _async/ - DO NOT EDIT DIRECTLY

# pyright: reportIncompatibleMethodOverride=false, reportImportCycles=false

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
from typing_extensions import override

from notte_sdk._sync.base import BaseClient, NotteEndpoint
from notte_sdk._sync.http import HTTPClient
from notte_sdk.types import (
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

if TYPE_CHECKING:
    from notte_sdk._sync.client import NotteClient


@final
class NotteVault(BaseVault, SyncResource):
    """Async vault that fetches credentials stored using the SDK."""

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
        self._vault_id: str | None = vault_id
        self._init_data = data

    @property
    def vault_id(self) -> str:
        if self._vault_id is None:
            raise ValueError("Vault not initialized. Call astart() first.")
        return self._vault_id

    @override
    def start(self) -> None:
        if self._vault_id is None:
            response = self.vault_client.create(**self._init_data)
            logger.warning(
                f"[Vault] {response.vault_id} created since no vault id was provided. Please store this to retrieve it later."
            )
            self._vault_id = response.vault_id
        else:
            _ = self.vault_client.list_credentials(self._vault_id)

    @override
    def stop(self) -> None:
        logger.info(f"[Vault] {self.vault_id} deleted. All credentials have been deleted.")
        self.delete()

    @override
    async def _add_credentials(self, url: str, creds: CredentialsDict) -> None:
        _ = self.vault_client.add_or_update_credentials(self.vault_id, url=url, **creds)

    @override
    async def _get_credentials_impl(self, url: str) -> CredentialsDict | None:
        result = self.vault_client.get_credentials(vault_id=self.vault_id, url=url)
        return result.credentials

    @override
    async def delete_credentials_async(self, url: str) -> None:
        _ = self.vault_client.delete_credentials(vault_id=self.vault_id, url=url)

    @override
    async def set_credit_card_async(self, **kwargs: Unpack[CreditCardDict]) -> None:
        _ = self.vault_client.set_credit_card(self.vault_id, **kwargs)

    @override
    async def get_credit_card_async(self) -> CreditCardDict:
        result = self.vault_client.get_credit_card(self.vault_id)
        return result.credit_card

    @override
    async def list_credentials_async(self) -> list[Credential]:
        result = self.vault_client.list_credentials(self.vault_id)
        return result.credentials

    @override
    async def delete_credit_card_async(self) -> None:
        _ = self.vault_client.delete_credit_card(self.vault_id)

    def delete(self) -> None:
        _ = self.vault_client.delete(self.vault_id)

    def generate_password(self, length: int = 20, include_special_chars: bool = True) -> str:
        """Generate a secure random password."""
        min_required_length = 4 if include_special_chars else 3
        if length < min_required_length:
            msg = f"Password length must be at least {min_required_length} characters"
            raise ValueError(msg)

        password = secrets.token_urlsafe(length)[:length]
        password_list = list(password)

        if not any(c.islower() for c in password_list):
            password_list[0] = secrets.choice("abcdefghijklmnopqrstuvwxyz")

        if not any(c.isupper() for c in password_list):
            idx = 1 if length > 1 else 0
            password_list[idx] = secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

        if not any(c.isdigit() for c in password_list):
            idx = 2 if length > 2 else 0
            password_list[idx] = secrets.choice("0123456789")

        if include_special_chars and not any(c in "!@#$%^&*()_+-=[]|;:,.<>?" for c in password_list):
            idx = 3 if length > 3 else 0
            password_list[idx] = secrets.choice("!@#$%^&*()_+-=[]|;:,.<>?")

        return "".join(password_list)


@final
class VaultsClient(BaseClient):
    """Async client for vault management."""

    # Vault endpoints
    CREATE_VAULT = "create"
    ADD_CREDENTIALS = "{vault_id}/credentials"
    GET_CREDENTIALS = "{vault_id}/credentials"
    DELETE_CREDENTIALS = "{vault_id}/credentials"
    ADD_CREDIT_CARD = "{vault_id}/card"
    GET_CREDIT_CARD = "{vault_id}/card"
    DELETE_CREDIT_CARD = "{vault_id}/card"
    LIST_VAULTS = ""
    LIST_CREDENTIALS = "{vault_id}"
    DELETE_VAULT = "{vault_id}"

    def __init__(
        self,
        root_client: "NotteClient",
        http_client: HTTPClient,
        server_url: str,
        api_key: str,
        verbose: bool = False,
    ):
        """Initialize VaultsClient."""
        super().__init__(
            root_client=root_client,
            base_endpoint_path="vaults",
            http_client=http_client,
            server_url=server_url,
            api_key=api_key,
            verbose=verbose,
        )

    @staticmethod
    def _delete_vault_endpoint(vault_id: str) -> NotteEndpoint[DeleteVaultResponse]:
        return NotteEndpoint(
            path=VaultsClient.DELETE_VAULT.format(vault_id=vault_id),
            response=DeleteVaultResponse,
            method="DELETE",
        )

    @staticmethod
    def _list_credentials_endpoint(vault_id: str) -> NotteEndpoint[ListCredentialsResponse]:
        return NotteEndpoint(
            path=VaultsClient.LIST_CREDENTIALS.format(vault_id=vault_id),
            response=ListCredentialsResponse,
            method="GET",
        )

    @staticmethod
    def _list_endpoint() -> NotteEndpoint[Vault]:
        return NotteEndpoint(
            path=VaultsClient.LIST_VAULTS,
            response=Vault,
            method="GET",
        )

    @staticmethod
    def _delete_credit_card_endpoint(vault_id: str) -> NotteEndpoint[DeleteCreditCardResponse]:
        return NotteEndpoint(
            path=VaultsClient.DELETE_CREDIT_CARD.format(vault_id=vault_id),
            response=DeleteCreditCardResponse,
            method="DELETE",
        )

    @staticmethod
    def _get_credit_card_endpoint(vault_id: str) -> NotteEndpoint[GetCreditCardResponse]:
        return NotteEndpoint(
            path=VaultsClient.GET_CREDIT_CARD.format(vault_id=vault_id),
            response=GetCreditCardResponse,
            method="GET",
        )

    @staticmethod
    def _set_credit_card_endpoint(vault_id: str) -> NotteEndpoint[AddCreditCardResponse]:
        return NotteEndpoint(
            path=VaultsClient.ADD_CREDIT_CARD.format(vault_id=vault_id),
            response=AddCreditCardResponse,
            method="POST",
        )

    @staticmethod
    def _delete_credentials_endpoint(vault_id: str) -> NotteEndpoint[DeleteCredentialsResponse]:
        return NotteEndpoint(
            path=VaultsClient.DELETE_CREDENTIALS.format(vault_id=vault_id),
            response=DeleteCredentialsResponse,
            method="DELETE",
        )

    @staticmethod
    def _get_credential_endpoint(vault_id: str) -> NotteEndpoint[GetCredentialsResponse]:
        return NotteEndpoint(
            path=VaultsClient.GET_CREDENTIALS.format(vault_id=vault_id),
            response=GetCredentialsResponse,
            method="GET",
        )

    @staticmethod
    def _add_or_update_credentials_endpoint(vault_id: str) -> NotteEndpoint[AddCredentialsResponse]:
        return NotteEndpoint(
            path=VaultsClient.ADD_CREDENTIALS.format(vault_id=vault_id),
            response=AddCredentialsResponse,
            method="POST",
        )

    @staticmethod
    def _create_vault_endpoint() -> NotteEndpoint[Vault]:
        return NotteEndpoint(
            path=VaultsClient.CREATE_VAULT,
            response=Vault,
            method="POST",
        )

    @track_usage("cloud.vault.create")
    def create(self, **data: Unpack[VaultCreateRequestDict]) -> Vault:
        """Create vault."""
        params = VaultCreateRequest.model_validate(data)
        return self.request(VaultsClient._create_vault_endpoint().with_request(params))

    def get(self, vault_id: str) -> str:
        if len(vault_id) == 0:
            raise ValueError("Vault ID cannot be empty")
        _ = self.list_credentials(vault_id)
        return vault_id

    @track_usage("cloud.vault.credentials.add")
    def add_or_update_credentials(
        self, vault_id: str, **data: Unpack[AddCredentialsRequestDict]
    ) -> AddCredentialsResponse:
        """Add or update credentials in a vault."""
        params = AddCredentialsRequest.from_dict(data)
        return self.request(self._add_or_update_credentials_endpoint(vault_id).with_request(params))

    @track_usage("cloud.vault.credentials.get")
    def get_credentials(self, vault_id: str, **data: Unpack[GetCredentialsRequestDict]) -> GetCredentialsResponse:
        """Retrieve credentials from a vault."""
        params = GetCredentialsRequest.model_validate(data)
        return self.request(self._get_credential_endpoint(vault_id).with_params(params))

    @track_usage("cloud.vault.credentials.delete")
    def delete_credentials(
        self, vault_id: str, **data: Unpack[DeleteCredentialsRequestDict]
    ) -> DeleteCredentialsResponse:
        """Delete credentials from a vault."""
        params = DeleteCredentialsRequest.model_validate(data)
        return self.request(self._delete_credentials_endpoint(vault_id).with_params(params))

    @track_usage("cloud.vault.delete")
    def delete(self, vault_id: str, **data: Unpack[DeleteVaultRequestDict]) -> DeleteVaultResponse:
        """Delete a vault."""
        params = DeleteVaultRequest.model_validate(data)
        return self.request(self._delete_vault_endpoint(vault_id).with_params(params))

    @track_usage("cloud.vault.credentials.list")
    def list_credentials(self, vault_id: str, **data: Unpack[ListCredentialsRequestDict]) -> ListCredentialsResponse:
        """List credentials in a vault."""
        params = ListCredentialsRequest.model_validate(data)
        return self.request(self._list_credentials_endpoint(vault_id).with_params(params))

    @track_usage("cloud.vault.list")
    def list(self, **data: Unpack[VaultListRequestDict]) -> Sequence[Vault]:
        """List all available vaults."""
        params = VaultListRequest.model_validate(data)
        endpoint = self._list_endpoint().with_params(params)
        return self.request_list(endpoint)

    @track_usage("cloud.vault.credit_card.delete")
    def delete_credit_card(
        self, vault_id: str, **data: Unpack[DeleteCreditCardRequestDict]
    ) -> DeleteCreditCardResponse:
        """Delete a credit card from a vault."""
        params = DeleteCreditCardRequest.model_validate(data)
        return self.request(self._delete_credit_card_endpoint(vault_id).with_params(params))

    @track_usage("cloud.vault.credit_card.get")
    def get_credit_card(self, vault_id: str, **data: Unpack[GetCreditCardRequestDict]) -> GetCreditCardResponse:
        """Retrieve a credit card from a vault."""
        params = GetCreditCardRequest.model_validate(data)
        return self.request(self._get_credit_card_endpoint(vault_id).with_params(params))

    @track_usage("cloud.vault.credit_card.set")
    def set_credit_card(self, vault_id: str, **data: Unpack[AddCreditCardRequestDict]) -> AddCreditCardResponse:
        """Set a credit card in a vault."""
        params = AddCreditCardRequest.from_dict(data)
        return self.request(self._set_credit_card_endpoint(vault_id).with_request(params))
