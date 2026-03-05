"""Async personas endpoint client for the Notte SDK."""
# Auto-generated from _async/ - DO NOT EDIT DIRECTLY

# pyright: reportImportCycles=false, reportPrivateUsage=false

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING, Unpack, overload

from notte_core.common.logging import logger
from notte_core.common.resource import SyncResource
from notte_core.common.telemetry import track_usage
from notte_core.credentials.base import BaseVault
from typing_extensions import final, override

from notte_sdk._sync.base import BaseClient, NotteEndpoint
from notte_sdk._sync.http import HTTPClient
from notte_sdk._sync.vaults import NotteVault
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
    from notte_sdk._sync.client import NotteClient


@final
class PersonasClient(BaseClient):
    """Async client for persona management."""

    # Persona endpoints
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
        http_client: HTTPClient,
        server_url: str,
        api_key: str,
        verbose: bool = False,
    ):
        """Initialize PersonasClient."""
        super().__init__(
            root_client=root_client,
            base_endpoint_path="personas",
            http_client=http_client,
            server_url=server_url,
            api_key=api_key,
            verbose=verbose,
        )

    @staticmethod
    def _list_emails_endpoint(persona_id: str) -> NotteEndpoint[EmailResponse]:
        return NotteEndpoint(
            path=PersonasClient.LIST_EMAILS.format(persona_id=persona_id),
            response=EmailResponse,
            method="GET",
        )

    @staticmethod
    def _list_sms_endpoint(persona_id: str) -> NotteEndpoint[SMSResponse]:
        return NotteEndpoint(
            path=PersonasClient.LIST_SMS.format(persona_id=persona_id),
            response=SMSResponse,
            method="GET",
        )

    @staticmethod
    def _create_number_endpoint(persona_id: str) -> NotteEndpoint[CreatePhoneNumberResponse]:
        return NotteEndpoint(
            path=PersonasClient.CREATE_NUMBER.format(persona_id=persona_id),
            response=CreatePhoneNumberResponse,
            method="POST",
        )

    @staticmethod
    def _delete_number_endpoint(persona_id: str) -> NotteEndpoint[DeletePhoneNumberResponse]:
        return NotteEndpoint(
            path=PersonasClient.DELETE_NUMBER.format(persona_id=persona_id),
            response=DeletePhoneNumberResponse,
            method="DELETE",
        )

    @staticmethod
    def _create_persona_endpoint() -> NotteEndpoint[PersonaResponse]:
        return NotteEndpoint(
            path=PersonasClient.CREATE_PERSONA,
            response=PersonaResponse,
            method="POST",
        )

    @staticmethod
    def _get_persona_endpoint(persona_id: str) -> NotteEndpoint[PersonaResponse]:
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
        """Create persona."""
        params = PersonaCreateRequest.model_validate(data)
        return self.request(PersonasClient._create_persona_endpoint().with_request(params))

    @track_usage("cloud.personas.get")
    def get(self, persona_id: str) -> PersonaResponse:
        """Get persona."""
        return self.request(PersonasClient._get_persona_endpoint(persona_id))

    @track_usage("cloud.personas.delete")
    def delete(self, persona_id: str) -> DeletePersonaResponse:
        """Delete persona."""
        return self.request(PersonasClient._delete_persona_endpoint(persona_id))

    @track_usage("cloud.personas.create_number")
    def create_number(self, persona_id: str, **data: Unpack[CreatePhoneNumberRequestDict]) -> CreatePhoneNumberResponse:
        """Create phone number for persona."""
        params = CreatePhoneNumberRequest.model_validate(data)
        return self.request(PersonasClient._create_number_endpoint(persona_id).with_request(params))

    @track_usage("cloud.personas.delete_number")
    def delete_number(self, persona_id: str) -> DeletePhoneNumberResponse:
        """Delete phone number for persona."""
        return self.request(PersonasClient._delete_number_endpoint(persona_id))

    @track_usage("cloud.personas.emails.list")
    def list_emails(self, persona_id: str, **data: Unpack[MessageReadRequestDict]) -> Sequence[EmailResponse]:
        """Read recent emails sent to the persona."""
        request = MessageReadRequest.model_validate(data)
        return self.request_list(PersonasClient._list_emails_endpoint(persona_id).with_params(request))

    @track_usage("cloud.personas.sms.list")
    def list_sms(self, persona_id: str, **data: Unpack[MessageReadRequestDict]) -> Sequence[SMSResponse]:
        """Read recent sms messages sent to the persona."""
        request = MessageReadRequest.model_validate(data)
        return self.request_list(PersonasClient._list_sms_endpoint(persona_id).with_params(request))

    def list(self, **data: Unpack[PersonaListRequestDict]) -> Sequence[PersonaResponse]:
        """List personas."""
        request = PersonaListRequest.model_validate(data)
        return self.request_list(PersonasClient._list_personas_endpoint().with_params(request))


class BasePersona(ABC):
    """Abstract base class for async personas."""

    @abstractmethod
    def emails(self, **data: Unpack[MessageReadRequestDict]) -> Sequence[EmailResponse]:
        raise NotImplementedError("Subclasses must implement this method")

    @abstractmethod
    def sms(self, **data: Unpack[MessageReadRequestDict]) -> Sequence[SMSResponse]:
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

    @property
    def has_vault(self) -> bool:
        return self.info.vault_id is not None


@final
class NottePersona(SyncResource, BasePersona):
    """Async self-service identity for web automation."""

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
        self._persona_id = persona_id

    @override
    def start(self) -> None:
        if self._persona_id is None:
            self._create()
            logger.warning(
                f"[Persona] {self.persona_id} created since no persona id was provided. Please store this to retrieve it later."
            )
        else:
            self.response = self.client.get(self._persona_id)

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
        self.delete()

    @override
    def _get_vault(self) -> NotteVault | None:
        if self.info.vault_id is None:
            return None
        vault = NotteVault(self.info.vault_id, _client=self.vault_client)
        vault.start()
        return vault

    def _create(self) -> None:
        if self.response is not None:
            raise ValueError(f"Persona {self.persona_id} already initialized")
        self.response = self.client.create(**self._init_request.model_dump(exclude_none=True))

    def delete(self) -> None:
        """Delete the persona."""
        _ = self.client.delete(self.persona_id)

    def add_credentials(self, url: str) -> None:
        """Add credentials to the persona."""
        vault = self._get_vault()
        if vault is None:
            raise ValueError(
                "Cannot add credentials to a persona without a vault. Please create a new persona using `create_vault=True` to use this feature."
            )
        password = vault.generate_password()
        asyncio.run(vault._add_credentials(url, {"email": self.info.email, "password": password}))

    @override
    def emails(self, **data: Unpack[MessageReadRequestDict]) -> Sequence[EmailResponse]:
        """Read recent emails sent to the persona."""
        return self.client.list_emails(self.persona_id, **data)

    @override
    def sms(self, **data: Unpack[MessageReadRequestDict]) -> Sequence[SMSResponse]:
        """Read recent SMS messages sent to the persona."""
        return self.client.list_sms(self.persona_id, **data)

    def create_number(self, **data: Unpack[CreatePhoneNumberRequestDict]) -> CreatePhoneNumberResponse:
        """Create a phone number for the persona."""
        return self.client.create_number(self.persona_id, **data)

    def delete_number(self) -> DeletePhoneNumberResponse:
        """Delete the phone number from the persona."""
        return self.client.delete_number(self.persona_id)
