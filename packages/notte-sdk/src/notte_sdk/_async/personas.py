"""Async personas endpoint client for the Notte SDK."""
# pyright: reportImportCycles=false, reportPrivateUsage=false

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING, Unpack, overload

from notte_core.common.logging import logger
from notte_core.common.resource import AsyncResource
from notte_core.common.telemetry import track_usage
from notte_core.credentials.base import BaseVault
from typing_extensions import final, override

from notte_sdk._async.base import AsyncBaseClient, NotteEndpoint
from notte_sdk._async.http import AsyncHTTPClient
from notte_sdk._async.vaults import AsyncNotteVault
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
    from notte_sdk._async.client import AsyncNotteClient


@final
class AsyncPersonasClient(AsyncBaseClient):
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
        root_client: "AsyncNotteClient",
        http_client: AsyncHTTPClient,
        server_url: str,
        api_key: str,
        verbose: bool = False,
    ):
        """Initialize AsyncPersonasClient."""
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
            path=AsyncPersonasClient.LIST_EMAILS.format(persona_id=persona_id),
            response=EmailResponse,
            method="GET",
        )

    @staticmethod
    def _list_sms_endpoint(persona_id: str) -> NotteEndpoint[SMSResponse]:
        return NotteEndpoint(
            path=AsyncPersonasClient.LIST_SMS.format(persona_id=persona_id),
            response=SMSResponse,
            method="GET",
        )

    @staticmethod
    def _create_number_endpoint(persona_id: str) -> NotteEndpoint[CreatePhoneNumberResponse]:
        return NotteEndpoint(
            path=AsyncPersonasClient.CREATE_NUMBER.format(persona_id=persona_id),
            response=CreatePhoneNumberResponse,
            method="POST",
        )

    @staticmethod
    def _delete_number_endpoint(persona_id: str) -> NotteEndpoint[DeletePhoneNumberResponse]:
        return NotteEndpoint(
            path=AsyncPersonasClient.DELETE_NUMBER.format(persona_id=persona_id),
            response=DeletePhoneNumberResponse,
            method="DELETE",
        )

    @staticmethod
    def _create_persona_endpoint() -> NotteEndpoint[PersonaResponse]:
        return NotteEndpoint(
            path=AsyncPersonasClient.CREATE_PERSONA,
            response=PersonaResponse,
            method="POST",
        )

    @staticmethod
    def _get_persona_endpoint(persona_id: str) -> NotteEndpoint[PersonaResponse]:
        return NotteEndpoint(
            path=AsyncPersonasClient.GET_PERSONA.format(persona_id=persona_id),
            response=PersonaResponse,
            method="GET",
        )

    @staticmethod
    def _delete_persona_endpoint(persona_id: str) -> NotteEndpoint[DeletePersonaResponse]:
        return NotteEndpoint(
            path=AsyncPersonasClient.DELETE_PERSONA.format(persona_id=persona_id),
            response=DeletePersonaResponse,
            method="DELETE",
        )

    @staticmethod
    def _list_personas_endpoint() -> NotteEndpoint[PersonaResponse]:
        return NotteEndpoint(
            path=AsyncPersonasClient.LIST_PERSONAS,
            response=PersonaResponse,
            method="GET",
        )

    @track_usage("cloud.personas.create")
    async def create(self, **data: Unpack[PersonaCreateRequestDict]) -> PersonaResponse:
        """Create persona."""
        params = PersonaCreateRequest.model_validate(data)
        return await self.request(AsyncPersonasClient._create_persona_endpoint().with_request(params))

    @track_usage("cloud.personas.get")
    async def get(self, persona_id: str) -> PersonaResponse:
        """Get persona."""
        return await self.request(AsyncPersonasClient._get_persona_endpoint(persona_id))

    @track_usage("cloud.personas.delete")
    async def delete(self, persona_id: str) -> DeletePersonaResponse:
        """Delete persona."""
        return await self.request(AsyncPersonasClient._delete_persona_endpoint(persona_id))

    @track_usage("cloud.personas.create_number")
    async def create_number(
        self, persona_id: str, **data: Unpack[CreatePhoneNumberRequestDict]
    ) -> CreatePhoneNumberResponse:
        """Create phone number for persona."""
        params = CreatePhoneNumberRequest.model_validate(data)
        return await self.request(AsyncPersonasClient._create_number_endpoint(persona_id).with_request(params))

    @track_usage("cloud.personas.delete_number")
    async def delete_number(self, persona_id: str) -> DeletePhoneNumberResponse:
        """Delete phone number for persona."""
        return await self.request(AsyncPersonasClient._delete_number_endpoint(persona_id))

    @track_usage("cloud.personas.emails.list")
    async def list_emails(self, persona_id: str, **data: Unpack[MessageReadRequestDict]) -> Sequence[EmailResponse]:
        """Read recent emails sent to the persona."""
        request = MessageReadRequest.model_validate(data)
        return await self.request_list(AsyncPersonasClient._list_emails_endpoint(persona_id).with_params(request))

    @track_usage("cloud.personas.sms.list")
    async def list_sms(self, persona_id: str, **data: Unpack[MessageReadRequestDict]) -> Sequence[SMSResponse]:
        """Read recent sms messages sent to the persona."""
        request = MessageReadRequest.model_validate(data)
        return await self.request_list(AsyncPersonasClient._list_sms_endpoint(persona_id).with_params(request))

    async def list(self, **data: Unpack[PersonaListRequestDict]) -> Sequence[PersonaResponse]:
        """List personas."""
        request = PersonaListRequest.model_validate(data)
        return await self.request_list(AsyncPersonasClient._list_personas_endpoint().with_params(request))


class AsyncBasePersona(ABC):
    """Abstract base class for async personas."""

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
    async def _aget_vault(self) -> BaseVault | None:
        raise NotImplementedError("Subclasses must implement this method")

    @property
    def info(self) -> PersonaResponse:
        return self._get_info()

    @property
    def has_vault(self) -> bool:
        return self.info.vault_id is not None


@final
class AsyncNottePersona(AsyncResource, AsyncBasePersona):
    """Async self-service identity for web automation."""

    @overload
    def __init__(self, /, persona_id: str, *, _client: "AsyncNotteClient | None" = None) -> None: ...

    @overload
    def __init__(
        self, *, _client: "AsyncNotteClient | None" = None, **data: Unpack[PersonaCreateRequestDict]
    ) -> None: ...

    def __init__(
        self,
        persona_id: str | None = None,
        *,
        _client: "AsyncNotteClient | None" = None,
        **data: Unpack[PersonaCreateRequestDict],
    ) -> None:
        if _client is None:
            raise ValueError("AsyncNotteClient is required")
        self._init_request = PersonaCreateRequest.model_validate(data)
        self.response: PersonaResponse | None = None
        self.client = _client.personas
        self.vault_client = _client.vaults
        self._persona_id = persona_id

    @override
    async def astart(self) -> None:
        if self._persona_id is None:
            await self._create()
            logger.warning(
                f"[Persona] {self.persona_id} created since no persona id was provided. Please store this to retrieve it later."
            )
        else:
            self.response = await self.client.get(self._persona_id)

    @property
    def persona_id(self) -> str:
        return self.info.persona_id

    @override
    def _get_info(self) -> PersonaResponse:
        if self.response is None:
            raise ValueError("Persona not initialized")
        return self.response

    @override
    async def astop(self) -> None:
        logger.info(f"[Persona] {self.persona_id} deleted.")
        await self.adelete()

    @override
    async def _aget_vault(self) -> AsyncNotteVault | None:
        if self.info.vault_id is None:
            return None
        vault = AsyncNotteVault(self.info.vault_id, _client=self.vault_client)
        await vault.astart()
        return vault

    async def _create(self) -> None:
        if self.response is not None:
            raise ValueError(f"Persona {self.persona_id} already initialized")
        self.response = await self.client.create(**self._init_request.model_dump(exclude_none=True))

    async def adelete(self) -> None:
        """Delete the persona."""
        _ = await self.client.delete(self.persona_id)

    async def add_credentials(self, url: str) -> None:
        """Add credentials to the persona."""
        vault = await self._aget_vault()
        if vault is None:
            raise ValueError(
                "Cannot add credentials to a persona without a vault. Please create a new persona using `create_vault=True` to use this feature."
            )
        password = vault.generate_password()
        await vault._add_credentials(url, {"email": self.info.email, "password": password})

    @override
    async def aemails(self, **data: Unpack[MessageReadRequestDict]) -> Sequence[EmailResponse]:
        """Read recent emails sent to the persona."""
        return await self.client.list_emails(self.persona_id, **data)

    @override
    async def asms(self, **data: Unpack[MessageReadRequestDict]) -> Sequence[SMSResponse]:
        """Read recent SMS messages sent to the persona."""
        return await self.client.list_sms(self.persona_id, **data)

    async def create_number(self, **data: Unpack[CreatePhoneNumberRequestDict]) -> CreatePhoneNumberResponse:
        """Create a phone number for the persona."""
        return await self.client.create_number(self.persona_id, **data)

    async def delete_number(self) -> DeletePhoneNumberResponse:
        """Delete the phone number from the persona."""
        return await self.client.delete_number(self.persona_id)
