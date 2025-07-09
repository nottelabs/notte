from collections.abc import Sequence
from typing import TYPE_CHECKING, Unpack

from loguru import logger
from notte_core.common.resource import SyncResource
from pydantic import BaseModel
from typing_extensions import final, override

from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from notte_sdk.endpoints.vaults import NotteVault, VaultsClient
from notte_sdk.types import (
    CreatePhoneNumberRequest,
    CreatePhoneNumberRequestDict,
    CreatePhoneNumberResponse,
    DeletePersonaResponse,
    DeletePhoneNumberResponse,
    EmailResponse,
    MessageReadRequest,
    MessageReadRequestDict,
    PersonaCreateRequest,
    PersonaCreateRequestDict,
    PersonaListRequest,
    PersonaListRequestDict,
    PersonaResponse,
    SMSResponse,
)

if TYPE_CHECKING:
    from notte_sdk.client import NotteClient


@final
class PersonasClient(BaseClient):
    """
    Client for the Notte API.

    Note: this client is only able to handle one session at a time.
    If you need to handle multiple sessions, you need to create a new client for each session.
    """

    # Session
    LIST_EMAILS = "{persona_id}/emails"
    LIST_SMS = "{persona_id}/sms"
    CREATE_NUMBER = "{persona_id}/sms/number"
    DELETE_NUMBER = "{persona_id}/sms/number"
    GET_PERSONA = "{persona_id}"
    CREATE_PERSONA = "create"
    DELETE_PERSONA = "{persona_id}"
    LIST_PERSONAS = ""

    def __init__(
        self,
        root_client: "NotteClient",
        api_key: str | None = None,
        server_url: str | None = None,
        verbose: bool = False,
    ):
        """
        Initialize a PersonasClient instance.

        Initializes the client with an optional API key for persona management.
        """
        super().__init__(
            root_client=root_client,
            base_endpoint_path="personas",
            server_url=server_url,
            api_key=api_key,
            verbose=verbose,
        )

    @override
    @staticmethod
    def endpoints() -> Sequence[NotteEndpoint[BaseModel]]:
        """Returns the available persona endpoints.

        Aggregates endpoints from PersonasClient for creating personas, reading messages, etc..."""
        return [
            PersonasClient._list_emails_endpoint(""),
            PersonasClient._list_sms_endpoint(""),
            PersonasClient._create_number_endpoint(""),
            PersonasClient._create_persona_endpoint(),
            PersonasClient._get_persona_endpoint(""),
            PersonasClient._delete_persona_endpoint(""),
            PersonasClient._delete_number_endpoint(""),
            PersonasClient._list_personas_endpoint(),
        ]

    @staticmethod
    def _list_emails_endpoint(persona_id: str) -> NotteEndpoint[EmailResponse]:
        """
        Returns a NotteEndpoint configured for reading persona emails.

        The returned endpoint uses the email_read path from PersonasClient with the GET method
        and expects a sequence of EmailResponse.
        """
        return NotteEndpoint(
            path=PersonasClient.LIST_EMAILS.format(persona_id=persona_id),
            response=EmailResponse,
            method="GET",
        )

    @staticmethod
    def _list_sms_endpoint(persona_id: str) -> NotteEndpoint[SMSResponse]:
        """
        Returns a NotteEndpoint configured for reading persona sms messages.

        The returned endpoint uses the sms_read path from PersonasClient with the GET method
        and expects a sequence of SMSResponse.
        """
        return NotteEndpoint(
            path=PersonasClient.LIST_SMS.format(persona_id=persona_id),
            response=SMSResponse,
            method="GET",
        )

    @staticmethod
    def _create_number_endpoint(persona_id: str) -> NotteEndpoint[CreatePhoneNumberResponse]:
        """
        Returns a NotteEndpoint configured for creating a virtual phone number.

        The returned endpoint uses the create number path from PersonasClient with the POST method returns a CreatePhoneNumberResponse.
        """
        return NotteEndpoint(
            path=PersonasClient.CREATE_NUMBER.format(persona_id=persona_id),
            response=CreatePhoneNumberResponse,
            method="POST",
        )

    @staticmethod
    def _delete_number_endpoint(persona_id: str) -> NotteEndpoint[DeletePhoneNumberResponse]:
        """
        Returns a NotteEndpoint configured for deleting a virtual phone number.
        """
        return NotteEndpoint(
            path=PersonasClient.DELETE_NUMBER.format(persona_id=persona_id),
            response=DeletePhoneNumberResponse,
            method="DELETE",
        )

    @staticmethod
    def _create_persona_endpoint() -> NotteEndpoint[PersonaResponse]:
        """
        Returns a NotteEndpoint configured for creating a persona.

        The returned endpoint uses the credentials from PersonasClient with the POST method and expects a PersonaCreateResponse.
        """
        return NotteEndpoint(
            path=PersonasClient.CREATE_PERSONA,
            response=PersonaResponse,
            method="POST",
        )

    @staticmethod
    def _get_persona_endpoint(persona_id: str) -> NotteEndpoint[PersonaResponse]:
        """
        Returns a NotteEndpoint configured for getting a persona.
        """
        return NotteEndpoint(
            path=PersonasClient.GET_PERSONA.format(persona_id=persona_id),
            response=PersonaResponse,
            method="GET",
        )

    @staticmethod
    def _delete_persona_endpoint(persona_id: str) -> NotteEndpoint[DeletePersonaResponse]:
        return NotteEndpoint(
            path=PersonasClient.DELETE_PERSONA.format(persona_id=persona_id),
            response=DeletePersonaResponse,
            method="DELETE",
        )

    @staticmethod
    def _list_personas_endpoint() -> NotteEndpoint[PersonaResponse]:
        return NotteEndpoint(
            path=PersonasClient.LIST_PERSONAS,
            response=PersonaResponse,
            method="GET",
        )

    def create(self, **data: Unpack[PersonaCreateRequestDict]) -> PersonaResponse:
        """
        Create persona

        Args:

        Returns:
            PersonaCreateResponse: The persona created
        """
        params = PersonaCreateRequest.model_validate(data)
        response = self.request(PersonasClient._create_persona_endpoint().with_request(params))
        return response

    def get(self, persona_id: str) -> PersonaResponse:
        """
        Get persona
        """
        response = self.request(PersonasClient._get_persona_endpoint(persona_id))
        return response

    def delete(self, persona_id: str) -> DeletePersonaResponse:
        """
        Delete persona
        """
        response = self.request(PersonasClient._delete_persona_endpoint(persona_id))
        return response

    def create_number(self, persona_id: str, **data: Unpack[CreatePhoneNumberRequestDict]) -> CreatePhoneNumberResponse:
        """
        Create phone number for persona (if one didn't exist before)

        Args:

        Returns:
            CreatePhoneNumberResponse: The status with the phone number that was created
        """
        params = CreatePhoneNumberRequest.model_validate(data)
        response = self.request(PersonasClient._create_number_endpoint(persona_id).with_request(params))
        return response

    def delete_number(self, persona_id: str) -> DeletePhoneNumberResponse:
        """
        Delete phone number for persona
        """
        return self.request(PersonasClient._delete_number_endpoint(persona_id))

    def list_emails(self, persona_id: str, **data: Unpack[MessageReadRequestDict]) -> Sequence[EmailResponse]:
        """
        Reads recent emails sent to the persona

        Args:
            **data: Keyword arguments representing details for querying emails.

        Returns:
            Sequence[EmailResponse]: The list of emails found
        """
        request = MessageReadRequest.model_validate(data)
        return self.request_list(PersonasClient._list_emails_endpoint(persona_id).with_params(request))

    def list_sms(self, persona_id: str, **data: Unpack[MessageReadRequestDict]) -> Sequence[SMSResponse]:
        """
        Reads recent sms messages sent to the persona

        Args:
            **data: Keyword arguments representing details for querying sms messages.

        Returns:
            Sequence[SMSResponse]: The list of sms messages found
        """
        request = MessageReadRequest.model_validate(data)
        return self.request_list(PersonasClient._list_sms_endpoint(persona_id).with_params(request))

    def list(self, **data: Unpack[PersonaListRequestDict]) -> Sequence[PersonaResponse]:
        """
        List personas
        """
        request = PersonaListRequest.model_validate(data)
        return self.request_list(PersonasClient._list_personas_endpoint().with_params(request))


@final
class Persona(SyncResource):
    def __init__(
        self, persona_id: str | None, request: PersonaCreateRequest, client: PersonasClient, vault_client: VaultsClient
    ):
        self._init_persona_id: str | None = persona_id
        self._init_request: PersonaCreateRequest = request
        self._info: PersonaResponse | None = None
        if self._init_persona_id is not None:
            self._info = client.get(self._init_persona_id)
        self.client = client
        self.vault_client = vault_client

    @override
    def start(self) -> None:
        if self._init_persona_id is None:
            _ = self.create(**self._init_request.model_dump(exclude_none=True))
        assert self._info is not None

    @property
    def persona_id(self) -> str:
        return self.info.persona_id

    @property
    def info(self) -> PersonaResponse:
        if self._info is None:
            raise ValueError("Persona not initialized")
        return self._info

    @override
    def stop(self) -> None:
        if self._init_persona_id is None:
            logger.info(f"[Persona] {self.persona_id} deleted.")
            _ = self.delete()

    @property
    def has_vault(self) -> bool:
        return self.info.vault_id is not None

    @property
    def vault(self) -> NotteVault:
        if self.info.vault_id is None:
            raise ValueError("Persona has no vault. Please create a new persona with a vault to use this feature.")
        return NotteVault(self.info.vault_id, self.vault_client)

    def create(self, **data: Unpack[PersonaCreateRequestDict]) -> PersonaResponse:
        if self._info is not None:
            raise ValueError("Persona already initialized")
        self._info = self.client.create(**data)
        return self._info

    def delete(self) -> None:
        _ = self.client.delete(self.persona_id)

    def emails(self, **data: Unpack[MessageReadRequestDict]) -> Sequence[EmailResponse]:
        return self.client.list_emails(self.persona_id, **data)

    def sms(self, **data: Unpack[MessageReadRequestDict]) -> Sequence[SMSResponse]:
        return self.client.list_sms(self.persona_id, **data)

    def create_number(self, **data: Unpack[CreatePhoneNumberRequestDict]) -> CreatePhoneNumberResponse:
        return self.client.create_number(self.persona_id, **data)

    def delete_number(self) -> DeletePhoneNumberResponse:
        return self.client.delete_number(self.persona_id)


@final
class RemotePersonaFactory:
    def __init__(self, client: PersonasClient, vault_client: VaultsClient):
        self.client = client
        self.vault_client = vault_client

    def __call__(self, persona_id: str | None = None, **data: Unpack[PersonaCreateRequestDict]) -> Persona:
        request = PersonaCreateRequest.model_validate(data)
        return Persona(persona_id, request, self.client, self.vault_client)
