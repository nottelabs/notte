from collections.abc import Sequence
from typing import Unpack

from pydantic import BaseModel
from typing_extensions import final, override

from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from notte_sdk.endpoints.personas import PersonasClient
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
    GetCreditCardResponse,
    ListCredentialsRequest,
    ListCredentialsRequestDict,
    ListCredentialsResponse,
    ListVaultsRequest,
    ListVaultsRequestDict,
    ListVaultsResponse,
    VaultCreateRequest,
    VaultCreateRequestDict,
    VaultCreateResponse,
)


@final
class VaultsClient(BaseClient):
    """
    Client for the Notte API.

    Note: this client is only able to handle one session at a time.
    If you need to handle multiple sessions, you need to create a new client for each session.
    """

    # Session
    CREATE_VAULT = "create"
    ADD_CREDENTIALS = "{vault_id}/credentials"
    GET_CREDENTIALS = "{vault_id}/credentials"
    DELETE_CREDENTIALS = "{vault_id}/credentials"
    ADD_CREDIT_CARD = "{vault_id}/card"
    GET_CREDIT_CARD = "{vault_id}/card"
    DELETE_CREDIT_CARD = "{vault_id}/card"
    LIST_VAULTS = "/"
    LIST_CREDENTIALS = "{vault_id}"
    DELETE_VAULT = "{vault_id}"

    @staticmethod
    def delete_vault_endpoint(vault_id: str) -> NotteEndpoint[DeleteVaultResponse]:
        """
        Returns a NotteEndpoint configured for deleting a vault.

        Args:
            vault_id: The ID of the vault to delete.

        Returns:
            A NotteEndpoint with the GET method that expects a DeleteVaultResponse.
        """
        return NotteEndpoint(
            path=VaultClient.DELETE_VAULT.format(vault_id=vault_id),
            response=DeleteVaultResponse,
            method="GET",
        )

    @staticmethod
    def list_credentials_endpoint(vault_id: str) -> NotteEndpoint[ListCredentialsResponse]:
        """
        Returns a NotteEndpoint configured for listing credentials in a vault.

        Args:
            vault_id: The ID of the vault to list credentials from.

        Returns:
            A NotteEndpoint with the GET method that expects a ListCredentialsResponse.
        """
        return NotteEndpoint(
            path=VaultClient.LIST_CREDENTIALS.format(vault_id=vault_id),
            response=ListCredentialsResponse,
            method="GET",
        )

    @staticmethod
    def list_endpoint() -> NotteEndpoint[ListVaultsResponse]:
        """
        Returns a NotteEndpoint configured for listing all vaults.

        Returns:
            A NotteEndpoint with the GET method that expects a ListVaultsResponse.
        """
        return NotteEndpoint(
            path=VaultClient.LIST_VAULTS,
            response=ListVaultsResponse,
            method="GET",
        )

    @staticmethod
    def delete_credit_card_endpoint(vault_id: str) -> NotteEndpoint[DeleteCreditCardResponse]:
        """
        Returns a NotteEndpoint configured for deleting a credit card from a vault.

        Args:
            vault_id: The ID of the vault containing the credit card to delete.

        Returns:
            A NotteEndpoint with the DELETE method that expects a DeleteCreditCardResponse.
        """
        return NotteEndpoint(
            path=VaultClient.DELETE_CREDIT_CARD.format(vault_id=vault_id),
            response=DeleteCreditCardResponse,
            method="DELETE",
        )

    @staticmethod
    def get_credit_card_endpoint(vault_id: str) -> NotteEndpoint[GetCreditCardResponse]:
        """
        Returns a NotteEndpoint configured for retrieving a credit card from a vault.

        Args:
            vault_id: The ID of the vault containing the credit card to retrieve.

        Returns:
            A NotteEndpoint with the GET method that expects a GetCreditCardResponse.
        """
        return NotteEndpoint(
            path=VaultClient.GET_CREDIT_CARD.format(vault_id=vault_id),
            response=GetCreditCardResponse,
            method="GET",
        )

    @staticmethod
    def set_credit_card_endpoint(vault_id: str) -> NotteEndpoint[AddCreditCardResponse]:
        """
        Returns a NotteEndpoint configured for setting a credit card in a vault.

        Args:
            vault_id: The ID of the vault to add the credit card to.

        Returns:
            A NotteEndpoint with the POST method that expects an AddCreditCardResponse.
        """
        return NotteEndpoint(
            path=VaultClient.ADD_CREDIT_CARD.format(vault_id=vault_id),
            response=AddCreditCardResponse,
            method="POST",
        )

    @staticmethod
    def delete_credentials_endpoint(vault_id: str) -> NotteEndpoint[DeleteCredentialsResponse]:
        """
        Returns a NotteEndpoint configured for deleting credentials from a vault.

        Args:
            vault_id: The ID of the vault containing the credentials to delete.

        Returns:
            A NotteEndpoint with the DELETE method that expects a DeleteCredentialsResponse.
        """
        return NotteEndpoint(
            path=VaultClient.DELETE_CREDENTIALS.format(vault_id=vault_id),
            response=DeleteCredentialsResponse,
            method="DELETE",
        )

    @staticmethod
    def get_credential_endpoint(vault_id: str) -> NotteEndpoint[GetCredentialsResponse]:
        """
        Returns a NotteEndpoint configured for retrieving credentials from a vault.

        Args:
            vault_id: The ID of the vault containing the credentials to retrieve.

        Returns:
            A NotteEndpoint with the GET method that expects a GetCredentialsResponse.
        """
        return NotteEndpoint(
            path=VaultClient.GET_CREDENTIALS.format(vault_id=vault_id),
            response=GetCredentialsResponse,
            method="GET",
        )

    @staticmethod
    def add_or_update_credentials_endpoint(vault_id: str) -> NotteEndpoint[AddCredentialsResponse]:
        """
        Returns a NotteEndpoint configured for adding or updating credentials in a vault.

        Args:
            vault_id: The ID of the vault to add or update credentials in.

        Returns:
            A NotteEndpoint with the POST method that expects an AddCredentialsResponse.
        """
        return NotteEndpoint(
            path=VaultClient.ADD_CREDENTIALS.format(vault_id=vault_id),
            response=AddCredentialsResponse,
            method="POST",
        )

    def __init__(
        self,
        persona_client: PersonasClient,
        api_key: str | None = None,
        verbose: bool = False,
    ):
        """
        Initialize a VaultsClient instance.

        Initializes the client with an optional API key for vault management.
        """
        super().__init__(base_endpoint_path="vaults", api_key=api_key, verbose=verbose)
        self.persona_client = persona_client

    @staticmethod
    def create_vault_endpoint() -> NotteEndpoint[VaultCreateResponse]:
        """
        Returns a NotteEndpoint configured for creating a new vault.

        Returns:
            A NotteEndpoint with the POST method that expects a VaultCreateResponse.
        """
        return NotteEndpoint(
            path=VaultClient.CREATE_VAULT,
            response=VaultCreateResponse,
            method="POST",
        )

    @override
    @staticmethod
    def endpoints() -> Sequence[NotteEndpoint[BaseModel]]:
        """Returns the available vault endpoints.

        Aggregates endpoints from PersonasClient for creating personas, reading messages, etc..."""
        return [
            VaultsClient.create_vault_endpoint(),
        ]

    def create_vault(self, **data: Unpack[VaultCreateRequestDict]) -> VaultCreateResponse:
        """
        Returns a NotteEndpoint configured for creating a persona.

        The returned endpoint uses the credentials from PersonasClient with the POST method and expects a PersonaCreateResponse.
        """
        return NotteEndpoint(
            path=VaultsClient.CREATE_VAULT,
            response=PersonaCreateResponse,
            method="POST",
        )

    def create(self, **data: Unpack[PersonaCreateRequestDict]) -> NotteVault:
        """
        Create vault

        Args:
            **data: Unpacked dictionary containing the vault creation parameters.

        Returns:
            VaultCreateResponse: Response from the vault creation endpoint.
        """
        params = PersonaCreateRequest.model_validate(data)
        response = self.request(VaultsClient.create_vault_endpoint().with_request(params))
        logger.info(f"Created vault with id: {response.persona_id}. Don't lose this id!")

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
        params = AddCredentialsRequest.model_validate(data)
        response = self.request(self.add_or_update_credentials_endpoint(vault_id).with_request(params))
        return response

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
        response = self.request(self.get_credential_endpoint(vault_id).with_params(params))
        return response

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
        response = self.request(self.delete_credentials_endpoint(vault_id).with_params(params))
        return response

    def delete_vault(self, vault_id: str, **data: Unpack[DeleteVaultRequestDict]) -> DeleteVaultResponse:
        """
        Deletes a vault.

        Args:
            vault_id: ID of the vault to delete.
            **data: Unpacked dictionary containing parameters for the request.

        Returns:
            DeleteVaultResponse: Response from the delete vault endpoint.
        """
        params = DeleteVaultRequest.model_validate(data)
        response = self.request(self.delete_vault_endpoint(vault_id).with_params(params))
        return response

    def list_credentials(self, vault_id: str, **data: Unpack[ListCredentialsRequestDict]) -> ListCredentialsResponse:
        """
        Lists credentials in a vault.

        Args:
            vault_id: ID of the vault to list credentials from.
            **data: Unpacked dictionary containing parameters for the request.

        Returns:
            ListCredentialsResponse: Response containing the list of credentials.
        """
        params = ListCredentialsRequest.model_validate(data)
        response = self.request(self.list_credentials_endpoint(vault_id).with_params(params))
        return response

    def list_vaults(self, **data: Unpack[ListVaultsRequestDict]) -> ListVaultsResponse:
        """
        Lists all available vaults.

        Args:
            **data: Unpacked dictionary containing parameters for the request.

        Returns:
            ListVaultsResponse: Response containing the list of vaults.
        """
        params = ListVaultsRequest.model_validate(data)
        response = self.request(self.list_endpoint().with_params(params))
        return response

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
        params = DeleteCreditCardRequest.model_validate(data)
        response = self.request(self.delete_credit_card_endpoint(vault_id).with_params(params))
        return response

    def get_credit_card(self, vault_id: str, **data: Unpack[GetCredentialsRequestDict]) -> GetCreditCardResponse:
        """
        Retrieves a credit card from a vault.

        Args:
            vault_id: ID of the vault containing the credit card.
            **data: Unpacked dictionary containing parameters for the request.

        Returns:
            GetCreditCardResponse: Response containing the requested credit card information.
        """
        params = GetCreditCardRequest.model_validate(data)
        response = self.request(self.get_credit_card_endpoint(vault_id).with_params(params))
        return response

    def set_credit_card(self, vault_id: str, **data: Unpack[AddCreditCardRequestDict]) -> AddCreditCardResponse:
        """
        Sets a credit card in a vault.

        Args:
            vault_id: ID of the vault to add the credit card to.
            **data: Unpacked dictionary containing credit card information.

        Returns:
            AddCreditCardResponse: Response from the add credit card endpoint.
        """
        params = AddCreditCardRequest.model_validate(data)
        response = self.request(self.set_credit_card_endpoint(vault_id).with_request(params))
        return response
