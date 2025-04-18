from collections.abc import Sequence
from typing import Unpack

from loguru import logger
from pydantic import BaseModel
from typing_extensions import final, override

from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from notte_sdk.endpoints.persona import PersonaClient
from notte_sdk.types import (
    PersonaCreateRequest,
    PersonaCreateRequestDict,
    PersonaCreateResponse,
)
from notte_sdk.vault import NotteVault


@final
class VaultClient(BaseClient):
    """
    Client for the Notte API.

    Note: this client is only able to handle one session at a time.
    If you need to handle multiple sessions, you need to create a new client for each session.
    """

    # Session
    CREATE_VAULT = "create"

    def __init__(
        self,
        persona_client: PersonaClient,
        api_key: str | None = None,
        verbose: bool = False,
    ):
        """
        Initialize a VaultClient instance.

        Initializes the client with an optional API key for vault management.
        """
        super().__init__(base_endpoint_path="vault", api_key=api_key, verbose=verbose)
        self.persona_client = persona_client

    def get(self, vault_id: str) -> NotteVault:
        return NotteVault(persona_client=self.persona_client, persona_id=vault_id)

    @override
    @staticmethod
    def endpoints() -> Sequence[NotteEndpoint[BaseModel]]:
        """Returns the available vault endpoints.

        Aggregates endpoints from PersonaClient for creating personas, reading messages, etc..."""
        return [
            VaultClient.create_vault_endpoint(),
        ]

    @staticmethod
    def create_vault_endpoint() -> NotteEndpoint[PersonaCreateResponse]:
        """
        Returns a NotteEndpoint configured for creating a persona.

        The returned endpoint uses the credentials from PersonaClient with the POST method and expects a PersonaCreateResponse.
        """
        return NotteEndpoint(
            path=VaultClient.CREATE_VAULT,
            response=PersonaCreateResponse,
            method="POST",
        )

    def create(self, **data: Unpack[PersonaCreateRequestDict]) -> NotteVault:
        """
        Create vault

        Args:

        Returns:
            PersonaCreateResponse: The persona created
        """
        params = PersonaCreateRequest.model_validate(data)
        response = self.request(VaultClient.create_vault_endpoint().with_request(params))
        logger.info(f"Created vault with id: {response.persona_id}. Don't lose this id!")

        return NotteVault(self.persona_client, persona_id=response.persona_id)
