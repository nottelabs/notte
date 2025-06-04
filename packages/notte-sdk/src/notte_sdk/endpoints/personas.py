from collections.abc import Sequence
from typing import Unpack

from pydantic import BaseModel
from typing_extensions import final, override

from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from notte_sdk.types import (
    EmailResponse,
    EmailsReadRequest,
    EmailsReadRequestDict,
    PersonaCreateRequest,
    PersonaCreateRequestDict,
    PersonaCreateResponse,
    SMSReadRequest,
    SMSReadRequestDict,
    SMSResponse,
    VirtualNumberRequest,
    VirtualNumberRequestDict,
    VirtualNumberResponse,
)


@final
class PersonasClient(BaseClient):
    """
    Client for the Notte API.

    Note: this client is only able to handle one session at a time.
    If you need to handle multiple sessions, you need to create a new client for each session.
    """

    # Session
    EMAILS_READ = "{persona_id}/email/read"
    SMS_READ = "{persona_id}/sms/read"
    CREATE_NUMBER = "{persona_id}/create-number"
    CREATE_PERSONA = "create"
    ADD_CREDENTIALS = "{persona_id}/credentials"
    GET_CREDENTIALS = "{persona_id}/credentials"
    DELETE_CREDENTIALS = "{persona_id}/credentials"

    def __init__(
        self,
        api_key: str | None = None,
        server_url: str | None = None,
        verbose: bool = False,
    ):
        """
        Initialize a PersonasClient instance.

        Initializes the client with an optional API key for persona management.
        """
        super().__init__(base_endpoint_path="personas", server_url=server_url, api_key=api_key, verbose=verbose)

    @override
    @staticmethod
    def endpoints() -> Sequence[NotteEndpoint[BaseModel]]:
        """Returns the available persona endpoints.

        Aggregates endpoints from PersonasClient for creating personas, reading messages, etc..."""
        return [
            PersonasClient.email_read_endpoint(""),
            PersonasClient.sms_read_endpoint(""),
            PersonasClient.create_number_endpoint(""),
            PersonasClient.create_persona_endpoint(),
        ]

    @staticmethod
    def email_read_endpoint(persona_id: str) -> NotteEndpoint[EmailResponse]:
        """
        Returns a NotteEndpoint configured for reading persona emails.

        The returned endpoint uses the email_read path from PersonasClient with the GET method
        and expects a sequence of EmailResponse.
        """
        return NotteEndpoint(
            path=PersonasClient.EMAILS_READ.format(persona_id=persona_id),
            response=EmailResponse,
            method="GET",
        )

    @staticmethod
    def sms_read_endpoint(persona_id: str) -> NotteEndpoint[SMSResponse]:
        """
        Returns a NotteEndpoint configured for reading persona sms messages.

        The returned endpoint uses the sms_read path from PersonasClient with the GET method
        and expects a sequence of SMSResponse.
        """
        return NotteEndpoint(
            path=PersonasClient.SMS_READ.format(persona_id=persona_id),
            response=SMSResponse,
            method="GET",
        )

    @staticmethod
    def create_number_endpoint(persona_id: str) -> NotteEndpoint[VirtualNumberResponse]:
        """
        Returns a NotteEndpoint configured for creating a virtual phone number.

        The returned endpoint uses the create number path from PersonasClient with the POST method and expects a VirtualNumberResponse.
        """
        return NotteEndpoint(
            path=PersonasClient.CREATE_NUMBER.format(persona_id=persona_id),
            response=VirtualNumberResponse,
            method="POST",
        )

    @staticmethod
    def create_persona_endpoint() -> NotteEndpoint[PersonaCreateResponse]:
        """
        Returns a NotteEndpoint configured for creating a persona.

        The returned endpoint uses the credentials from PersonasClient with the POST method and expects a PersonaCreateResponse.
        """
        return NotteEndpoint(
            path=PersonasClient.CREATE_PERSONA,
            response=PersonaCreateResponse,
            method="POST",
        )

    def create_persona(self, **data: Unpack[PersonaCreateRequestDict]) -> PersonaCreateResponse:
        """
        Create persona

        Args:

        Returns:
            PersonaCreateResponse: The persona created
        """
        params = PersonaCreateRequest.model_validate(data)
        response = self.request(PersonasClient.create_persona_endpoint().with_request(params))
        return response

    def create_number(self, persona_id: str, **data: Unpack[VirtualNumberRequestDict]) -> VirtualNumberResponse:
        """
        Create phone number for persona (if one didn't exist before)

        Args:

        Returns:
            VirtualNumberResponse: The status
        """
        params = VirtualNumberRequest.model_validate(data)
        response = self.request(PersonasClient.create_number_endpoint(persona_id).with_request(params))
        return response

    def email_read(self, persona_id: str, **data: Unpack[EmailsReadRequestDict]) -> Sequence[EmailResponse]:
        """
        Reads recent emails sent to the persona

        Args:
            **data: Keyword arguments representing details for querying emails.

        Returns:
            Sequence[EmailResponse]: The list of emails found
        """
        request = EmailsReadRequest.model_validate(data)
        response = self.request_list(PersonasClient.email_read_endpoint(persona_id).with_params(request))
        return response

    def sms_read(self, persona_id: str, **data: Unpack[SMSReadRequestDict]) -> Sequence[SMSResponse]:
        """
        Reads recent sms messages sent to the persona

        Args:
            **data: Keyword arguments representing details for querying sms messages.

        Returns:
            Sequence[SMSResponse]: The list of sms messages found
        """
        request = SMSReadRequest.model_validate(data)
        response = self.request_list(PersonasClient.sms_read_endpoint(persona_id).with_params(request))
        return response
