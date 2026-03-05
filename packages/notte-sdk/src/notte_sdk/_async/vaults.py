"""Async vaults endpoint client for the Notte SDK."""
# pyright: reportIncompatibleMethodOverride=false, reportImportCycles=false

from __future__ import annotations

import secrets
from collections.abc import Sequence
from typing import TYPE_CHECKING, Unpack, final, overload

from notte_core.common.logging import logger
from notte_core.common.resource import AsyncResource
from notte_core.common.telemetry import track_usage
from notte_core.credentials.base import (
    BaseVault,
    Credential,
    CredentialsDict,
    CreditCardDict,
    Vault,
)
from typing_extensions import override

from notte_sdk._async.base import AsyncBaseClient, NotteEndpoint
from notte_sdk._async.http import AsyncHTTPClient
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
    from notte_sdk._async.client import AsyncNotteClient


@final
class AsyncNotteVault(BaseVault, AsyncResource):
    """Async vault that fetches credentials stored using the SDK."""

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

        self.vault_client = _client
        self._vault_id: str | None = vault_id
        self._init_data = data

    @property
    def vault_id(self) -> str:
        if self._vault_id is None:
            raise ValueError("Vault not initialized. Call astart() first.")
        return self._vault_id

    @override
    async def astart(self) -> None:
        if self._vault_id is None:
            response = await self.vault_client.create(**self._init_data)
            logger.warning(
                f"[Vault] {response.vault_id} created since no vault id was provided. Please store this to retrieve it later."
            )
            self._vault_id = response.vault_id
        else:
            _ = await self.vault_client.list_credentials(self._vault_id)

    @override
    async def astop(self) -> None:
        logger.info(f"[Vault] {self.vault_id} deleted. All credentials have been deleted.")
        await self.adelete()

    @override
    async def _add_credentials(self, url: str, creds: CredentialsDict) -> None:
        _ = await self.vault_client.add_or_update_credentials(self.vault_id, url=url, **creds)

    @override
    async def _get_credentials_impl(self, url: str) -> CredentialsDict | None:
        result = await self.vault_client.get_credentials(vault_id=self.vault_id, url=url)
        return result.credentials

    @override
    async def delete_credentials_async(self, url: str) -> None:
        _ = await self.vault_client.delete_credentials(vault_id=self.vault_id, url=url)

    @override
    async def set_credit_card_async(self, **kwargs: Unpack[CreditCardDict]) -> None:
        _ = await self.vault_client.set_credit_card(self.vault_id, **kwargs)

    @override
    async def get_credit_card_async(self) -> CreditCardDict:
        result = await self.vault_client.get_credit_card(self.vault_id)
        return result.credit_card

    @override
    async def list_credentials_async(self) -> list[Credential]:
        result = await self.vault_client.list_credentials(self.vault_id)
        return result.credentials

    @override
    async def delete_credit_card_async(self) -> None:
        _ = await self.vault_client.delete_credit_card(self.vault_id)

    async def adelete(self) -> None:
        _ = await self.vault_client.delete(self.vault_id)

    # Override sync methods from BaseVault to be async (avoid asyncio.run in async context)
    async def add_credentials(self, url: str, **kwargs: Unpack[CredentialsDict]) -> None:  # type: ignore[override]
        """Store credentials for a given URL (async version)."""
        return await self.add_credentials_async(url, **kwargs)

    async def set_credit_card(self, **kwargs: Unpack[CreditCardDict]) -> None:  # type: ignore[override]
        """Store credit card information (async version)."""
        return await self.set_credit_card_async(**kwargs)

    async def get_credit_card(self) -> CreditCardDict:  # type: ignore[override]
        """Retrieve credit card information (async version)."""
        return await self.get_credit_card_async()

    async def delete_credit_card(self) -> None:  # type: ignore[override]
        """Remove saved credit card information (async version)."""
        return await self.delete_credit_card_async()

    async def delete_credentials(self, url: str) -> None:  # type: ignore[override]
        """Remove credentials for a given URL (async version)."""
        return await self.delete_credentials_async(url)

    async def list_credentials(self) -> list[Credential]:  # type: ignore[override]
        """List urls for which we hold credentials (async version)."""
        return await self.list_credentials_async()

    async def has_credential(self, url: str) -> bool:  # type: ignore[override]
        """Check whether we hold a credential for a given website (async version)."""
        return await self.has_credential_async(url)

    async def add_credentials_from_env(self, url: str) -> None:  # type: ignore[override]
        """Add credentials from environment variables for a given URL (async version)."""
        return await self.add_credentials_from_env_async(url)

    async def get_credentials(self, url: str) -> CredentialsDict | None:  # type: ignore[override]
        """Get credentials for a given URL (async version)."""
        return await self.get_credentials_async(url)

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
class AsyncVaultsClient(AsyncBaseClient):
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
        root_client: "AsyncNotteClient",
        http_client: AsyncHTTPClient,
        server_url: str,
        api_key: str,
        verbose: bool = False,
    ):
        """Initialize AsyncVaultsClient."""
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
            path=AsyncVaultsClient.DELETE_VAULT.format(vault_id=vault_id),
            response=DeleteVaultResponse,
            method="DELETE",
        )

    @staticmethod
    def _list_credentials_endpoint(vault_id: str) -> NotteEndpoint[ListCredentialsResponse]:
        return NotteEndpoint(
            path=AsyncVaultsClient.LIST_CREDENTIALS.format(vault_id=vault_id),
            response=ListCredentialsResponse,
            method="GET",
        )

    @staticmethod
    def _list_endpoint() -> NotteEndpoint[Vault]:
        return NotteEndpoint(
            path=AsyncVaultsClient.LIST_VAULTS,
            response=Vault,
            method="GET",
        )

    @staticmethod
    def _delete_credit_card_endpoint(vault_id: str) -> NotteEndpoint[DeleteCreditCardResponse]:
        return NotteEndpoint(
            path=AsyncVaultsClient.DELETE_CREDIT_CARD.format(vault_id=vault_id),
            response=DeleteCreditCardResponse,
            method="DELETE",
        )

    @staticmethod
    def _get_credit_card_endpoint(vault_id: str) -> NotteEndpoint[GetCreditCardResponse]:
        return NotteEndpoint(
            path=AsyncVaultsClient.GET_CREDIT_CARD.format(vault_id=vault_id),
            response=GetCreditCardResponse,
            method="GET",
        )

    @staticmethod
    def _set_credit_card_endpoint(vault_id: str) -> NotteEndpoint[AddCreditCardResponse]:
        return NotteEndpoint(
            path=AsyncVaultsClient.ADD_CREDIT_CARD.format(vault_id=vault_id),
            response=AddCreditCardResponse,
            method="POST",
        )

    @staticmethod
    def _delete_credentials_endpoint(vault_id: str) -> NotteEndpoint[DeleteCredentialsResponse]:
        return NotteEndpoint(
            path=AsyncVaultsClient.DELETE_CREDENTIALS.format(vault_id=vault_id),
            response=DeleteCredentialsResponse,
            method="DELETE",
        )

    @staticmethod
    def _get_credential_endpoint(vault_id: str) -> NotteEndpoint[GetCredentialsResponse]:
        return NotteEndpoint(
            path=AsyncVaultsClient.GET_CREDENTIALS.format(vault_id=vault_id),
            response=GetCredentialsResponse,
            method="GET",
        )

    @staticmethod
    def _add_or_update_credentials_endpoint(vault_id: str) -> NotteEndpoint[AddCredentialsResponse]:
        return NotteEndpoint(
            path=AsyncVaultsClient.ADD_CREDENTIALS.format(vault_id=vault_id),
            response=AddCredentialsResponse,
            method="POST",
        )

    @staticmethod
    def _create_vault_endpoint() -> NotteEndpoint[Vault]:
        return NotteEndpoint(
            path=AsyncVaultsClient.CREATE_VAULT,
            response=Vault,
            method="POST",
        )

    @track_usage("cloud.vault.create")
    async def create(self, **data: Unpack[VaultCreateRequestDict]) -> Vault:
        """Create vault."""
        params = VaultCreateRequest.model_validate(data)
        return await self.request(AsyncVaultsClient._create_vault_endpoint().with_request(params))

    async def get(self, vault_id: str) -> str:
        if len(vault_id) == 0:
            raise ValueError("Vault ID cannot be empty")
        _ = await self.list_credentials(vault_id)
        return vault_id

    @track_usage("cloud.vault.credentials.add")
    async def add_or_update_credentials(
        self, vault_id: str, **data: Unpack[AddCredentialsRequestDict]
    ) -> AddCredentialsResponse:
        """Add or update credentials in a vault."""
        params = AddCredentialsRequest.from_dict(data)
        return await self.request(self._add_or_update_credentials_endpoint(vault_id).with_request(params))

    @track_usage("cloud.vault.credentials.get")
    async def get_credentials(self, vault_id: str, **data: Unpack[GetCredentialsRequestDict]) -> GetCredentialsResponse:
        """Retrieve credentials from a vault."""
        params = GetCredentialsRequest.model_validate(data)
        return await self.request(self._get_credential_endpoint(vault_id).with_params(params))

    @track_usage("cloud.vault.credentials.delete")
    async def delete_credentials(
        self, vault_id: str, **data: Unpack[DeleteCredentialsRequestDict]
    ) -> DeleteCredentialsResponse:
        """Delete credentials from a vault."""
        params = DeleteCredentialsRequest.model_validate(data)
        return await self.request(self._delete_credentials_endpoint(vault_id).with_params(params))

    @track_usage("cloud.vault.delete")
    async def delete(self, vault_id: str, **data: Unpack[DeleteVaultRequestDict]) -> DeleteVaultResponse:
        """Delete a vault."""
        params = DeleteVaultRequest.model_validate(data)
        return await self.request(self._delete_vault_endpoint(vault_id).with_params(params))

    @track_usage("cloud.vault.credentials.list")
    async def list_credentials(
        self, vault_id: str, **data: Unpack[ListCredentialsRequestDict]
    ) -> ListCredentialsResponse:
        """List credentials in a vault."""
        params = ListCredentialsRequest.model_validate(data)
        return await self.request(self._list_credentials_endpoint(vault_id).with_params(params))

    @track_usage("cloud.vault.list")
    async def list(self, **data: Unpack[VaultListRequestDict]) -> Sequence[Vault]:
        """List all available vaults."""
        params = VaultListRequest.model_validate(data)
        endpoint = self._list_endpoint().with_params(params)
        return await self.request_list(endpoint)

    @track_usage("cloud.vault.credit_card.delete")
    async def delete_credit_card(
        self, vault_id: str, **data: Unpack[DeleteCreditCardRequestDict]
    ) -> DeleteCreditCardResponse:
        """Delete a credit card from a vault."""
        params = DeleteCreditCardRequest.model_validate(data)
        return await self.request(self._delete_credit_card_endpoint(vault_id).with_params(params))

    @track_usage("cloud.vault.credit_card.get")
    async def get_credit_card(self, vault_id: str, **data: Unpack[GetCreditCardRequestDict]) -> GetCreditCardResponse:
        """Retrieve a credit card from a vault."""
        params = GetCreditCardRequest.model_validate(data)
        return await self.request(self._get_credit_card_endpoint(vault_id).with_params(params))

    @track_usage("cloud.vault.credit_card.set")
    async def set_credit_card(self, vault_id: str, **data: Unpack[AddCreditCardRequestDict]) -> AddCreditCardResponse:
        """Set a credit card in a vault."""
        params = AddCreditCardRequest.from_dict(data)
        return await self.request(self._set_credit_card_endpoint(vault_id).with_request(params))
