from collections.abc import Sequence
from typing import Any, Unpack

from notte_core.credentials.base import CredentialField
from pydantic import BaseModel
from typing_extensions import final, override

from notte_sdk.endpoints.base import BaseClient, NotteEndpoint
from notte_sdk.errors import NotteAPIError
from notte_sdk.types import (
    AddCredentialsRequest,
    AddCredentialsRequestDict,
    AddCredentialsResponse,
    DeleteCredentialsRequest,
    DeleteCredentialsRequestDict,
    DeleteCredentialsResponse,
    EmailResponse,
    EmailsReadRequest,
    EmailsReadRequestDict,
    GetCredentialsRequest,
    GetCredentialsRequestDict,
    GetCredentialsResponse,
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
class PersonaClient(BaseClient):
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
        verbose: bool = False,
    ):
        """
        Initialize a PersonaClient instance.

        Initializes the client with an optional API key for persona management.
        """
        super().__init__(base_endpoint_path="personas", api_key=api_key, verbose=verbose)

    @override
    @staticmethod
    def endpoints() -> Sequence[NotteEndpoint[BaseModel]]:
        """Returns the available persona endpoints.

        Aggregates endpoints from PersonaClient for creating personas, reading messages, etc..."""
        return [
            PersonaClient.email_read_endpoint(""),
            PersonaClient.sms_read_endpoint(""),
            PersonaClient.create_number_endpoint(""),
            PersonaClient.create_persona_endpoint(),
            PersonaClient.add_credentials_endpoint(""),
            PersonaClient.get_credentials_endpoint(""),
            PersonaClient.delete_credentials_endpoint(""),
        ]

    @staticmethod
    def email_read_endpoint(persona_id: str) -> NotteEndpoint[EmailResponse]:
        """
        Returns a NotteEndpoint configured for reading persona emails.

        The returned endpoint uses the email_read path from PersonaClient with the GET method
        and expects a sequence of EmailResponse.
        """
        return NotteEndpoint(
            path=PersonaClient.EMAILS_READ.format(persona_id=persona_id),
            response=EmailResponse,
            method="GET",
        )

    @staticmethod
    def sms_read_endpoint(persona_id: str) -> NotteEndpoint[SMSResponse]:
        """
        Returns a NotteEndpoint configured for reading persona sms messages.

        The returned endpoint uses the sms_read path from PersonaClient with the GET method
        and expects a sequence of SMSResponse.
        """
        return NotteEndpoint(
            path=PersonaClient.SMS_READ.format(persona_id=persona_id),
            response=SMSResponse,
            method="GET",
        )

    @staticmethod
    def create_number_endpoint(persona_id: str) -> NotteEndpoint[VirtualNumberResponse]:
        """
        Returns a NotteEndpoint configured for creating a virtual phone number.

        The returned endpoint uses the create number path from PersonaClient with the POST method and expects a VirtualNumberResponse.
        """
        return NotteEndpoint(
            path=PersonaClient.CREATE_NUMBER.format(persona_id=persona_id),
            response=VirtualNumberResponse,
            method="POST",
        )

    @staticmethod
    def create_persona_endpoint() -> NotteEndpoint[PersonaCreateResponse]:
        """
        Returns a NotteEndpoint configured for creating a persona.

        The returned endpoint uses the credentials from PersonaClient with the POST method and expects a PersonaCreateResponse.
        """
        return NotteEndpoint(
            path=PersonaClient.CREATE_PERSONA,
            response=PersonaCreateResponse,
            method="POST",
        )

    @staticmethod
    def add_credentials_endpoint(persona_id: str) -> NotteEndpoint[AddCredentialsResponse]:
        """
        Returns a NotteEndpoint configured for adding credentials.

        The returned endpoint uses the credentials from PersonaClient with the POST method and expects an AddCredentialsResponse.
        """
        return NotteEndpoint(
            path=PersonaClient.ADD_CREDENTIALS.format(persona_id=persona_id),
            response=AddCredentialsResponse,
            method="POST",
        )

    @staticmethod
    def get_credentials_endpoint(persona_id: str) -> NotteEndpoint[GetCredentialsResponse]:
        """
        Returns a NotteEndpoint configured for getting credentials.

        The returned endpoint uses the credentials from PersonaClient with the GET method and expects a GetCredentialsResponse.
        """
        return NotteEndpoint(
            path=PersonaClient.GET_CREDENTIALS.format(persona_id=persona_id),
            response=GetCredentialsResponse,
            method="GET",
        )

    @staticmethod
    def delete_credentials_endpoint(persona_id: str) -> NotteEndpoint[DeleteCredentialsResponse]:
        """
        Returns a NotteEndpoint configured for deleting credentials.

        The returned endpoint uses the create persona path from PersonaClient with the DELETE method and expects a DeleteCredentialsResponse.
        """
        return NotteEndpoint(
            path=PersonaClient.DELETE_CREDENTIALS.format(persona_id=persona_id),
            response=DeleteCredentialsResponse,
            method="DELETE",
        )

    def add_credentials(self, persona_id: str, **data: Unpack[AddCredentialsRequestDict]) -> AddCredentialsResponse:
        """
        Add credentials

        Args:
            persona_id: The ID of the persona to add credentials to
            **data: Query parameters including:
                url: Website url for which to add credentials (if None, singleton credentials)
                credentials: The credentials to add

        Returns:
            AddCredentialsResponse: status for added credentials
        """
        params = AddCredentialsRequest.from_request_dict(data)
        response = self.request(PersonaClient.add_credentials_endpoint(persona_id).with_request(params))
        return response

    def get_credentials(self, persona_id: str, **data: Unpack[GetCredentialsRequestDict]) -> GetCredentialsResponse:
        """
        Get credentials

        Args:
            persona_id: The ID of the persona to get credentials from
            **data: Query parameters including:
                url: Website url for which to get credentials (if None, return singleton credentials)

        Returns:
            GetCredentialsResponse: returned credentials
        """
        params = GetCredentialsRequest.model_validate(data)
        endpoint = PersonaClient.get_credentials_endpoint(persona_id).with_params(params)

        # need to do some trickery to build Creds
        response: Any = self._request(endpoint)
        if not isinstance(response, dict):
            raise NotteAPIError(path=endpoint.path, response=response)

        creds = [CredentialField.from_dict(field) for field in response["credentials"]]  # type: ignore

        return GetCredentialsResponse(credentials=creds)

    def delete_credentials(
        self, persona_id: str, **data: Unpack[DeleteCredentialsRequestDict]
    ) -> DeleteCredentialsResponse:
        """
        Delete credentials

        Args:
            persona_id: The ID of the persona for which we remove credentials
            **data: Query parameters including:
                url: Website url for which we remove credentials (if None, delete singleton credentials)

        Returns:
            DeleteCredentialsResponse: status for deleted credentials
        """
        params = DeleteCredentialsRequest.model_validate(data)
        response = self.request(PersonaClient.delete_credentials_endpoint(persona_id).with_params(params))
        return response

    def create_persona(self, **data: Unpack[PersonaCreateRequestDict]) -> PersonaCreateResponse:
        """
        Create persona

        Args:

        Returns:
            PersonaCreateResponse: The persona created
        """
        params = PersonaCreateRequest.model_validate(data)
        response = self.request(PersonaClient.create_persona_endpoint().with_request(params))
        return response

    def create_number(self, persona_id: str, **data: Unpack[VirtualNumberRequestDict]) -> VirtualNumberResponse:
        """
        Create phone number for persona (if one didn't exist before)

        Args:

        Returns:
            VirtualNumberResponse: The status
        """
        params = VirtualNumberRequest.model_validate(data)
        response = self.request(PersonaClient.create_number_endpoint(persona_id).with_request(params))
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
        response = self.request_list(PersonaClient.email_read_endpoint(persona_id).with_params(request))
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
        response = self.request_list(PersonaClient.sms_read_endpoint(persona_id).with_params(request))
        return response
