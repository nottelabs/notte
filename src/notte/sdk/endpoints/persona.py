from collections.abc import Sequence
from typing import Unpack

from pydantic import BaseModel
from typing_extensions import final, override

from notte.sdk.endpoints.base import BaseClient, NotteEndpoint
from notte.sdk.types import (
    EmailResponse,
    EmailsReadRequest,
    EmailsReadRequestDict,
    SMSReadRequest,
    SMSReadRequestDict,
    SMSResponse,
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

    def __init__(
        self,
        api_key: str | None = None,
    ):
        """
        Initialize a SessionsClient instance.

        Initializes the client with an optional API key and server URL for session management,
        setting the base endpoint to "sessions". Also initializes the last session response to None.
        """
        super().__init__(base_endpoint_path="persona", api_key=api_key)

    @override
    @staticmethod
    def endpoints() -> Sequence[NotteEndpoint[BaseModel]]:
        """Returns a sequence of available session endpoints.

        Aggregates endpoints from SessionsClient for starting, closing, status checking, listing,
        and debugging sessions (including tab-specific debugging)."""
        return [
            PersonaClient.email_read_endpoint(""),
        ]

    @staticmethod
    def email_read_endpoint(persona_id: str) -> NotteEndpoint[EmailResponse]:
        """
        Returns a NotteEndpoint configured for starting a session.

        The returned endpoint uses the session start path from SessionsClient with the POST method and expects a SessionResponse.
        """
        return NotteEndpoint(
            path=PersonaClient.EMAILS_READ.format(persona_id=persona_id),
            response=EmailResponse,
            method="GET",
        )

    @staticmethod
    def sms_read_endpoint(persona_id: str) -> NotteEndpoint[SMSResponse]:
        """
        Returns a NotteEndpoint configured for starting a session.

        The returned endpoint uses the session start path from SessionsClient with the POST method and expects a SessionResponse.
        """
        return NotteEndpoint(
            path=PersonaClient.SMS_READ.format(persona_id=persona_id),
            response=SMSResponse,
            method="GET",
        )

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
