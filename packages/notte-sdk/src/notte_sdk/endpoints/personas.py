import asyncio
import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from functools import cached_property
from typing import TYPE_CHECKING, Generic, TypeVar, Unpack, overload
from urllib.parse import quote

from notte_core._sync import run_sync
from notte_core.credentials.base import BaseVault, VaultState
from notte_core.logging import logger
from notte_core.resource import SyncResource
from notte_core.telemetry import track_usage
from typing_extensions import final, override

from notte_sdk._generated.resources import AsyncPersonasOperations, PersonasOperations
from notte_sdk._requests import wire_request
from notte_sdk.endpoints._async_resource import AwaitableResource
from notte_sdk.endpoints.base import NotteEndpoint
from notte_sdk.endpoints.vaults import AsyncNotteVault, AsyncVaultsClient, NotteVault
from notte_sdk.types import (
    CreatePhoneNumberRequest,
    CreatePhoneNumberRequestDict,
    CreatePhoneNumberResponse,
    DeletePhoneNumberResponse,
    EmailResponse,
    MessageReadRequestDict,
    PersonaCreateRequest,
    PersonaCreateRequestDict,
    PersonaResponse,
    SMSResponse,
)

if TYPE_CHECKING:
    from notte_sdk.client import AsyncNotteClient, NotteClient

_NO_VAULT = "Persona has no vault. Please create a new persona using `create_vault=True` to use this feature."
_NO_VAULT_FOR_CREDENTIALS = "Cannot add credentials to a persona without a vault. Please create a new persona using `create_vault=True` to use this feature."


def _phone_number_path(persona_id: str) -> str:
    # Served by the API but missing from its OpenAPI schema, so there is no generated endpoint.
    return f"/personas/{quote(persona_id, safe='')}/sms/number"


def _create_number_endpoint(
    persona_id: str, data: CreatePhoneNumberRequestDict
) -> NotteEndpoint[CreatePhoneNumberResponse]:
    params = CreatePhoneNumberRequest.model_validate(data)
    endpoint = NotteEndpoint(path=_phone_number_path(persona_id), response=CreatePhoneNumberResponse, method="POST")
    return endpoint.with_request(params)


def _delete_number_endpoint(persona_id: str) -> NotteEndpoint[DeletePhoneNumberResponse]:
    return NotteEndpoint(path=_phone_number_path(persona_id), response=DeletePhoneNumberResponse, method="DELETE")


def _log_created(persona_id: str) -> None:
    logger.warning(
        f"[Persona] {persona_id} created since no persona id was provided. Please store this to retrieve it later."
    )


def _already_deleted(error: Exception) -> bool:
    """Whether the error of a persona deletion says the persona was already gone."""
    message = str(error).lower()
    return "already" in message and ("deleted" in message or "not found" in message)


@final
class PersonasClient(PersonasOperations):
    """
    Client for the Notte API.

    Note: this client is only able to handle one session at a time.
    If you need to handle multiple sessions, you need to create a new client for each session.
    """

    # Legacy: phone-number routes are absent from the committed OpenAPI schema.
    @track_usage("cloud.personas.create_number")
    def create_number(self, persona_id: str, **data: Unpack[CreatePhoneNumberRequestDict]) -> CreatePhoneNumberResponse:
        """
        Create phone number for persona (if one didn't exist before)

        Args:

        Returns:
            CreatePhoneNumberResponse: The status with the phone number that was created
        """
        return self.request(_create_number_endpoint(persona_id, data))

    @track_usage("cloud.personas.delete_number")
    def delete_number(self, persona_id: str) -> DeletePhoneNumberResponse:
        """
        Delete phone number for persona
        """
        return self.request(_delete_number_endpoint(persona_id))


@final
class AsyncPersonasClient(AsyncPersonasOperations):
    """`PersonasClient` for `AsyncNotteClient`."""

    # Legacy: phone-number routes are absent from the committed OpenAPI schema.
    @track_usage("cloud.personas.create_number")
    async def create_number(
        self, persona_id: str, **data: Unpack[CreatePhoneNumberRequestDict]
    ) -> CreatePhoneNumberResponse:
        """
        Create phone number for persona (if one didn't exist before)

        Args:

        Returns:
            CreatePhoneNumberResponse: The status with the phone number that was created
        """
        return await self.request(_create_number_endpoint(persona_id, data))

    @track_usage("cloud.personas.delete_number")
    async def delete_number(self, persona_id: str) -> DeletePhoneNumberResponse:
        """
        Delete phone number for persona
        """
        return await self.request(_delete_number_endpoint(persona_id))


TVault = TypeVar("TVault", bound=VaultState)


class _PersonaInfo(Generic[TVault], ABC):
    @abstractmethod
    def _get_info(self) -> PersonaResponse:
        raise NotImplementedError("Subclasses must implement this method")

    @abstractmethod
    def _get_vault(self) -> TVault | None:
        raise NotImplementedError("Subclasses must implement this method")

    @property
    def info(self) -> PersonaResponse:
        return self._get_info()

    @property
    def email(self) -> str:
        """Readable email address intended for external senders."""
        return self.info.email

    @property
    def internal_email(self) -> str:
        """Stable UUID-backed address for the persona mailbox."""
        return self.info.internal_email

    @cached_property
    def vault(self) -> TVault:
        vault = self._get_vault()
        if vault is None:
            raise ValueError(_NO_VAULT)
        return vault

    @property
    def has_vault(self) -> bool:
        return self.info.vault_id is not None


class _SyncPersonaInbox(ABC):
    @abstractmethod
    def emails(self, **data: Unpack[MessageReadRequestDict]) -> Sequence[EmailResponse]: ...

    @abstractmethod
    def sms(self, **data: Unpack[MessageReadRequestDict]) -> Sequence[SMSResponse]: ...

    def wait_for_emails(
        self, *, timeout: float = 60.0, poll_interval: float = 5.0, **data: Unpack[MessageReadRequestDict]
    ) -> Sequence[EmailResponse]:
        """
        Poll the persona inbox until at least one email matches, e.g. to read a sign-up code.

        ```python
        emails = persona.wait_for_emails(only_unread=True, timeout=120)
        ```

        Raises `TimeoutError` if nothing arrives within `timeout` seconds. Listed emails are marked as read.
        """
        deadline = time.monotonic() + timeout
        while not (emails := self.emails(**data)):
            if time.monotonic() + poll_interval > deadline:
                raise TimeoutError(f"No email received within {timeout}s")
            time.sleep(poll_interval)
        return emails

    def wait_for_sms(
        self, *, timeout: float = 60.0, poll_interval: float = 5.0, **data: Unpack[MessageReadRequestDict]
    ) -> Sequence[SMSResponse]:
        """
        Poll the persona inbox until at least one SMS matches, e.g. to read a 2FA code.

        ```python
        sms = persona.wait_for_sms(only_unread=True, timeout=120)
        ```

        Raises `TimeoutError` if nothing arrives within `timeout` seconds. Listed SMS are marked as read.
        """
        deadline = time.monotonic() + timeout
        while not (sms := self.sms(**data)):
            if time.monotonic() + poll_interval > deadline:
                raise TimeoutError(f"No SMS received within {timeout}s")
            time.sleep(poll_interval)
        return sms


class BasePersona(_PersonaInfo[BaseVault], _SyncPersonaInbox, ABC):
    @abstractmethod
    async def aemails(self, **data: Unpack[MessageReadRequestDict]) -> Sequence[EmailResponse]:
        raise NotImplementedError("Subclasses must implement this method")

    @abstractmethod
    async def asms(self, **data: Unpack[MessageReadRequestDict]) -> Sequence[SMSResponse]:
        raise NotImplementedError("Subclasses must implement this method")

    async def await_emails(
        self, *, timeout: float = 60.0, poll_interval: float = 5.0, **data: Unpack[MessageReadRequestDict]
    ) -> Sequence[EmailResponse]:
        """Poll the inbox until at least one email matches `data` (e.g. `only_unread=True`); see `wait_for_emails`."""
        deadline = time.monotonic() + timeout
        while not (emails := await self.aemails(**data)):
            if time.monotonic() + poll_interval > deadline:
                raise TimeoutError(f"No email received within {timeout}s")
            await asyncio.sleep(poll_interval)
        return emails

    async def await_sms(
        self, *, timeout: float = 60.0, poll_interval: float = 5.0, **data: Unpack[MessageReadRequestDict]
    ) -> Sequence[SMSResponse]:
        """Poll the inbox until at least one SMS matches `data`; see `wait_for_sms`."""
        deadline = time.monotonic() + timeout
        while not (sms := await self.asms(**data)):
            if time.monotonic() + poll_interval > deadline:
                raise TimeoutError(f"No SMS received within {timeout}s")
            await asyncio.sleep(poll_interval)
        return sms

    # Sync methods
    @override
    def emails(self, **data: Unpack[MessageReadRequestDict]) -> Sequence[EmailResponse]:
        return run_sync(self.aemails(**data))

    @override
    def sms(self, **data: Unpack[MessageReadRequestDict]) -> Sequence[SMSResponse]:
        return run_sync(self.asms(**data))


@final
class NottePersona(SyncResource, _PersonaInfo[NotteVault], _SyncPersonaInbox):
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
        self._init_request = wire_request(PersonaCreateRequest, data)
        self.response: PersonaResponse | None = None
        self.client = _client.personas
        self.vault_client = _client.vaults

        if persona_id is None:
            self.create()
            _log_created(self.persona_id)
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
        try:
            _ = self.delete()
            logger.info(f"[Persona] {self.persona_id} deleted.")
        except Exception as e:
            if _already_deleted(e):
                logger.warning(f"[Persona] {self.persona_id} was already deleted.")
            else:
                raise

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
            raise ValueError(_NO_VAULT_FOR_CREDENTIALS)
        password = vault.generate_password()
        vault.add_credentials(url, email=self.info.email, password=password)

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
        return self.client.emails_list(self.persona_id, **data)

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
        return self.client.sms_list(self.persona_id, **data)

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


@final
class AsyncNottePersona(AwaitableResource, BasePersona):
    """
    `NottePersona` for `AsyncNotteClient`: the same methods, as coroutines.

    ```python
    async with client.Persona(create_vault=True) as persona:
        emails = await persona.wait_for_emails(only_unread=True, timeout=120)
    ```

    `persona = await client.Persona(...)` creates the persona, or fetches `persona_id`, like the
    `NottePersona` constructor; `async with` also deletes it on exit. `persona.vault` is an
    `AsyncNotteVault`; `await persona.vault` checks that it exists, like the sync property.
    """

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
        self._init_request = wire_request(PersonaCreateRequest, data)
        self._requested_id: str | None = persona_id
        self.response: PersonaResponse | None = None
        self.client: AsyncPersonasClient = _client.personas
        self.vault_client: AsyncVaultsClient = _client.vaults

    @override
    async def _start(self) -> None:
        """Create the persona, or fetch `persona_id`, unless that was already done."""
        if self.response is not None:
            return
        if self._requested_id is None:
            await self.create()
            _log_created(self.persona_id)
        else:
            self.response = await self.client.get(self._requested_id)

    @property
    def persona_id(self) -> str:
        return self.info.persona_id

    @override
    def _get_info(self) -> PersonaResponse:
        if self.response is None:
            raise ValueError("Persona not initialized: `await` it or use `async with` first")
        return self.response

    @override
    async def stop(self) -> None:
        try:
            await self.delete()
            logger.info(f"[Persona] {self.persona_id} deleted.")
        except Exception as e:
            if _already_deleted(e):
                logger.warning(f"[Persona] {self.persona_id} was already deleted.")
            else:
                raise

    @override
    def _get_vault(self) -> AsyncNotteVault | None:
        if self.info.vault_id is None:
            return None
        return AsyncNotteVault(self.info.vault_id, _client=self.vault_client)

    @cached_property
    @override
    def vault(self) -> AsyncNotteVault:
        vault = self._get_vault()
        if vault is None:
            raise ValueError(_NO_VAULT)
        return vault

    async def create(self) -> None:
        if self.response is not None:
            raise ValueError(f"Persona {self.persona_id} already initialized")
        self.response = await self.client.create(**self._init_request.model_dump(exclude_none=True))

    async def delete(self) -> None:
        """
        Delete the persona from the notte console.

        ```python
        persona = await notte.Persona("<your-persona-id>")
        await persona.delete()
        ```
        """
        _ = await self.client.delete(self.persona_id)

    async def add_credentials(self, url: str) -> None:
        """
        Add credentials to the persona (generates a password and stores it in the vault)
        """
        vault = self._get_vault()
        if vault is None:
            raise ValueError(_NO_VAULT_FOR_CREDENTIALS)
        # Checks that the vault exists, like the `NotteVault` constructor.
        _ = await vault
        password = vault.generate_password()
        await vault.add_credentials(url, email=self.info.email, password=password)

    @override
    async def aemails(self, **data: Unpack[MessageReadRequestDict]) -> Sequence[EmailResponse]:
        return await self.emails(**data)

    @override
    async def emails(self, **data: Unpack[MessageReadRequestDict]) -> Sequence[EmailResponse]:  # pyright: ignore[reportIncompatibleMethodOverride]
        """
        Read recent emails sent to the persona; see `NottePersona.emails`.

        ```python
        emails = await persona.emails(only_unread=True)
        ```

        Be careful once emails are listed, they are considered read.
        """
        return await self.client.emails_list(self.persona_id, **data)

    @override
    async def asms(self, **data: Unpack[MessageReadRequestDict]) -> Sequence[SMSResponse]:
        return await self.sms(**data)

    @override
    async def sms(self, **data: Unpack[MessageReadRequestDict]) -> Sequence[SMSResponse]:  # pyright: ignore[reportIncompatibleMethodOverride]
        """
        Read recent sms messages sent to the persona; see `NottePersona.sms`.

        ```python
        sms = await persona.sms(only_unread=True)
        ```

        Be careful once sms are listed, they are considered read.
        """
        return await self.client.sms_list(self.persona_id, **data)

    @override
    async def wait_for_emails(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, *, timeout: float = 60.0, poll_interval: float = 5.0, **data: Unpack[MessageReadRequestDict]
    ) -> Sequence[EmailResponse]:
        """
        Poll the persona inbox until at least one email matches, e.g. to read a sign-up code.

        ```python
        emails = await persona.wait_for_emails(only_unread=True, timeout=120)
        ```

        Raises `TimeoutError` if nothing arrives within `timeout` seconds. Listed emails are marked as read.
        """
        return await self.await_emails(timeout=timeout, poll_interval=poll_interval, **data)

    @override
    async def wait_for_sms(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, *, timeout: float = 60.0, poll_interval: float = 5.0, **data: Unpack[MessageReadRequestDict]
    ) -> Sequence[SMSResponse]:
        """
        Poll the persona inbox until at least one SMS matches, e.g. to read a 2FA code.

        ```python
        sms = await persona.wait_for_sms(only_unread=True, timeout=120)
        ```

        Raises `TimeoutError` if nothing arrives within `timeout` seconds. Listed SMS are marked as read.
        """
        return await self.await_sms(timeout=timeout, poll_interval=poll_interval, **data)

    async def create_number(self, **data: Unpack[CreatePhoneNumberRequestDict]) -> CreatePhoneNumberResponse:
        """
        Create a phone number to the persona.

        ```python
        persona = await notte.Persona("<your-persona-id>")
        await persona.create_number()
        ```
        """
        return await self.client.create_number(self.persona_id, **data)

    async def delete_number(self) -> DeletePhoneNumberResponse:
        """
        Delete the phone number from the persona.

        ```python
        persona = await notte.Persona("<your-persona-id>")
        await persona.delete_number()
        ```
        """
        return await self.client.delete_number(self.persona_id)
