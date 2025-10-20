import asyncio
from abc import ABC, abstractmethod
from collections.abc import Sequence
from functools import cached_property
from typing import TYPE_CHECKING, Unpack, overload

from notte_core.common.logging import logger
from notte_core.common.resource import SyncResource
from notte_core.common.telemetry import track_usage
from notte_core.credentials.base import BaseVault
from typing_extensions import final, override

from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from notte_sdk.endpoints.vaults import NotteVault
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

    @track_usage("cloud.personas.create")
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

    @track_usage("cloud.personas.get")
    def get(self, persona_id: str) -> PersonaResponse:
        """
        Get persona
        """
        response = self.request(PersonasClient._get_persona_endpoint(persona_id))
        return response

    @track_usage("cloud.personas.delete")
    def delete(self, persona_id: str) -> DeletePersonaResponse:
        """
        Delete persona
        """
        response = self.request(PersonasClient._delete_persona_endpoint(persona_id))
        return response

    @track_usage("cloud.personas.create_number")
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

    @track_usage("cloud.personas.delete_number")
    def delete_number(self, persona_id: str) -> DeletePhoneNumberResponse:
        """
        Delete phone number for persona
        """
        return self.request(PersonasClient._delete_number_endpoint(persona_id))

    @track_usage("cloud.personas.emails.list")
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

    @track_usage("cloud.personas.sms.list")
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


class BasePersona(ABC):
    @abstractmethod
    async def aemails(self, **data: Unpack[MessageReadRequestDict]) -> Sequence[EmailResponse]:
        raise NotImplementedError("Subclasses must implement this method")

    @abstractmethod
    async def asms(self, **data: Unpack[MessageReadRequestDict]) -> Sequence[SMSResponse]:
        raise NotImplementedError("Subclasses must implement this method")

    @abstractmethod
    def _get_info(self) -> PersonaResponse:
        raise NotImplementedError("Subclasses must implement this method")

    @abstractmethod
    def _get_vault(self) -> BaseVault | None:
        raise NotImplementedError("Subclasses must implement this method")

    @property
    def info(self) -> PersonaResponse:
        return self._get_info()

    @cached_property
    def vault(self) -> BaseVault:
        vault = self._get_vault()
        if vault is None:
            raise ValueError(
                "Persona has no vault. Please create a new persona using `create_vault=True` to use this feature."
            )
        return vault

    @property
    def has_vault(self) -> bool:
        return self.info.vault_id is not None

    # Sync methods
    def emails(self, **data: Unpack[MessageReadRequestDict]) -> Sequence[EmailResponse]:
        return asyncio.run(self.aemails(**data))

    def sms(self, **data: Unpack[MessageReadRequestDict]) -> Sequence[SMSResponse]:
        return asyncio.run(self.asms(**data))


@final
class NottePersona(SyncResource, BasePersona):
    """
    Self-service identities for web automation (account creation, 2FA,etc.).

    Notte Personas provide automated identity management for AI agents, enabling them to create accounts, handle two-factor authentication, and interact with web platforms without manual intervention.

    Notte Personas come with complete digital identities:
    - Unique Email Address: Dedicated mailbox for each persona with full email management
    - Phone Number: SMS-capable phone number for verification and 2FA
    - Credential Vault: Optional secure storage for passwords and authentication tokens
    - Automated Communication: Built-in email and SMS reading capabilities
    - 2FA Support: Seamless handling of two-factor authentication flows
    """

    @overload
    def __init__(self, /, persona_id: str, *, _client: "NotteClient | None" = None) -> None: ...

    @overload
    def __init__(self, *, _client: "NotteClient | None" = None, **data: Unpack[PersonaCreateRequestDict]) -> None: ...

    def __init__(
        self,
        persona_id: str | None = None,
        *,
        _client: "NotteClient | None" = None,
        **data: Unpack[PersonaCreateRequestDict],
    ) -> None:
        if _client is None:
            raise ValueError("NotteClient is required")
        self._init_request = PersonaCreateRequest.model_validate(data)
        self.response: PersonaResponse | None = None
        self.client = _client.personas
        self.vault_client = _client.vaults

        if persona_id is None:
            self.create()
            logger.warning(
                f"[Persona] {self.persona_id} created since no persona id was provided. Please store this to retrieve it later."
            )
        else:
            self.response = _client.personas.get(persona_id)

    @override
    def start(self) -> None:
        if self.response is None:
            _ = self.create(**self._init_request.model_dump(exclude_none=True))
        assert self.response is not None

    @property
    def persona_id(self) -> str:
        return self.info.persona_id

    @override
    def _get_info(self) -> PersonaResponse:
        if self.response is None:
            raise ValueError("Persona not initialized")
        return self.response

    @override
    def stop(self) -> None:
        logger.info(f"[Persona] {self.persona_id} deleted.")
        _ = self.delete()

    @override
    def _get_vault(self) -> NotteVault | None:
        if self.info.vault_id is None:
            return None
        return NotteVault(self.info.vault_id, _client=self.vault_client)

    def create(self) -> None:
        if self.response is not None:
            raise ValueError(f"Persona {self.persona_id} already initialized")
        self.response = self.client.create(**self._init_request.model_dump(exclude_none=True))

    def delete(self) -> None:
        """
        Delete the persona from the notte console.

        ```python
        persona = notte.Persona("<your-persona-id>")
        persona.delete()
        ```
        """
        _ = self.client.delete(self.persona_id)

    def add_credentials(self, url: str) -> None:
        """
        Add credentials to the persona (generates a password and stores it in the vault)
        """
        vault = self._get_vault()
        if vault is None:
            raise ValueError(
                "Cannot add credentials to a persona without a vault. Please create a new persona using `create_vault=True` to use this feature."
            )
        password = vault.generate_password()
        vault.add_credentials(url, email=self.info.email, password=password)

    @override
    async def aemails(self, **data: Unpack[MessageReadRequestDict]) -> Sequence[EmailResponse]:
        return self.emails(**data)

    @override
    def emails(self, **data: Unpack[MessageReadRequestDict]) -> Sequence[EmailResponse]:
        """
        Read recent emails sent to the persona.

        ```python
        persona = notte.Persona("<your-persona-id>")
        emails = persona.emails()
        ```

        You can also filter the emails by using the `only_unread` parameter.

        ```python
        emails = persona.emails(only_unread=True)
        ```

        Be careful once emails are listed, they are considered read.


        Use the `limit` and/or `timedelta` parameters to limit the number of emails returned.
        """
        return self.client.list_emails(self.persona_id, **data)

    @override
    async def asms(self, **data: Unpack[MessageReadRequestDict]) -> Sequence[SMSResponse]:
        return self.sms(**data)

    @override
    def sms(self, **data: Unpack[MessageReadRequestDict]) -> Sequence[SMSResponse]:
        """
        Read recent sms messages sent to the persona.

        ```python
        persona = notte.Persona("<your-persona-id>")
        sms = persona.sms()
        ```

        You can also filter the sms by using the `only_unread` parameter.

        ```python
        sms = persona.sms(only_unread=True)
        ```

        Be careful once sms are listed, they are considered read.

        Use the `limit` and/or `timedelta` parameters to limit the number of sms returned.
        """
        return self.client.list_sms(self.persona_id, **data)

    def create_number(self, **data: Unpack[CreatePhoneNumberRequestDict]) -> CreatePhoneNumberResponse:
        """
        Create a phone number to the persona.

        ```python
        persona = notte.Persona("<your-persona-id>")
        persona.create_number()
        ```
        """
        return self.client.create_number(self.persona_id, **data)

    def delete_number(self) -> DeletePhoneNumberResponse:
        """
        Delete the phone number from the persona.

        ```python
        persona = notte.Persona("<your-persona-id>")
        persona.delete_number()
        ```
        """
        return self.client.delete_number(self.persona_id)
