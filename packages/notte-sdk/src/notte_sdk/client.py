# pyright: reportImportCycles=false
import math
import os
import weakref
from functools import partial
from types import TracebackType
from typing import Any, Literal, Self, Unpack, cast, overload

from notte_core import enable_nest_asyncio
from notte_core.actions import GotoAction
from notte_core.data import StructuredData, TBaseModel
from notte_core.logging import logger
from notte_core.types import ScrapeMarkdownParamsDict, ScrapeRequestDict
from pydantic import BaseModel
from typing_extensions import final

from notte_sdk._generated.resources import (
    AsyncProfilesOperations,
    AsyncSessionsOperations,
)
from notte_sdk._retry import DEFAULT_MAX_RETRIES
from notte_sdk._transport import AsyncSharedHttpClient, SharedHttpClient
from notte_sdk.auth import MISSING_API_KEY_MESSAGE, resolve_api_key
from notte_sdk.endpoints.base import BaseClient
from notte_sdk.endpoints.files import (
    AsyncFileStorageClient,
    AsyncRemoteFileStorage,
    FileStorageClient,
    RemoteFileStorage,
)
from notte_sdk.endpoints.functions import AsyncFunctionsClient, AsyncNotteFunction, FunctionsClient, NotteFunction
from notte_sdk.endpoints.managed_auth import AsyncManagedAuthClient, ManagedAuthClient
from notte_sdk.endpoints.personas import AsyncNottePersona, AsyncPersonasClient, NottePersona, PersonasClient
from notte_sdk.endpoints.profiles import ProfilesClient
from notte_sdk.endpoints.sessions import RemoteSession, SessionsClient, SessionViewerType
from notte_sdk.endpoints.vaults import AsyncNotteVault, AsyncVaultsClient, NotteVault, VaultsClient
from notte_sdk.errors import AuthenticationError

enable_nest_asyncio()


def _validated_settings(
    api_key: str | None, server_url: str | None, captcha_timeout_seconds: float, max_retries: int
) -> str:
    """Check the client settings shared by `NotteClient` and `AsyncNotteClient`; returns the API key."""
    if not math.isfinite(captcha_timeout_seconds) or captcha_timeout_seconds <= 0:
        raise ValueError("captcha_timeout_seconds must be finite and greater than zero")
    if type(max_retries) is not int or max_retries < 0:
        raise ValueError("max_retries must be a non-negative integer")
    # Resolve once so the keyring is read at most once per client.
    api_key = resolve_api_key(api_key, server_url or os.getenv("NOTTE_API_URL") or BaseClient.DEFAULT_NOTTE_API_URL)
    if api_key is None:
        raise AuthenticationError(MISSING_API_KEY_MESSAGE)
    return api_key


@final
class NotteClient:
    """
    Client for the Notte API.

    Note: this client is only able to handle one session at a time.
    If you need to handle multiple sessions, you need to create a new client for each session.
    """

    def __init__(
        self,
        api_key: str | None = None,
        server_url: str | None = None,
        verbose: bool = False,
        viewer_type: SessionViewerType = SessionViewerType.BROWSER,
        captcha_timeout_seconds: float = 180,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        """Initialize a NotteClient instance.

        Initializes the NotteClient with the specified API key and server URL, creating instances
        of SessionsClient, FunctionsClient, VaultsClient, and PersonasClient.

        Args:
            api_key: Optional API key for authentication.
            captcha_timeout_seconds: Total CAPTCHA wait budget, separate from action and HTTP timeouts.
            max_retries: Retries for transient failures (502, 503, 504, 529, and connection errors),
                with exponential backoff and full jitter. ``Retry-After`` is honored. POST and PATCH
                requests are only retried when the API cannot have processed them (503, 529,
                connection refused), so they are never applied twice. Set to 0 to disable retries.
        """

        api_key = _validated_settings(api_key, server_url, captcha_timeout_seconds, max_retries)
        self.captcha_timeout_seconds: float = captcha_timeout_seconds
        self.max_retries: int = max_retries
        # One connection pool for every resource client below.
        self._http: SharedHttpClient = SharedHttpClient()
        _ = weakref.finalize(self, self._http.close)
        self.sessions: SessionsClient = SessionsClient(
            root_client=self, api_key=api_key, server_url=server_url, verbose=verbose, viewer_type=viewer_type
        )
        self.personas: PersonasClient = PersonasClient(
            root_client=self, api_key=api_key, server_url=server_url, verbose=verbose
        )
        self.vaults: VaultsClient = VaultsClient(
            root_client=self, api_key=api_key, server_url=server_url, verbose=verbose
        )
        self.profiles: ProfilesClient = ProfilesClient(
            root_client=self, api_key=api_key, server_url=server_url, verbose=verbose
        )
        self.managed_auth: ManagedAuthClient = ManagedAuthClient(
            root_client=self, api_key=api_key, server_url=server_url, verbose=verbose
        )
        self.files: FileStorageClient = FileStorageClient(
            root_client=self, api_key=api_key, server_url=server_url, verbose=verbose
        )
        self.functions: FunctionsClient = FunctionsClient(
            root_client=self, api_key=api_key, server_url=server_url, verbose=verbose
        )

        if self.sessions.server_url != self.sessions.DEFAULT_NOTTE_API_URL:
            logger.warning(f"NOTTE_API_URL is set to: {self.sessions.server_url}")

    def close(self) -> None:
        """Close pooled HTTP connections.

        Connections are also closed when the client is garbage collected. The
        client stays usable: a later request opens a new connection.
        """
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def Session(self) -> type[RemoteSession]:
        return cast(type[RemoteSession], partial(RemoteSession, _client=self.sessions))

    @property
    def Vault(self) -> type[NotteVault]:
        return cast(type[NotteVault], partial(NotteVault, _client=self.vaults))

    @property
    def Persona(self) -> type[NottePersona]:
        return cast(type[NottePersona], partial(NottePersona, _client=self))

    @property
    def FileStorage(self) -> type[RemoteFileStorage]:
        return cast(type[RemoteFileStorage], partial(RemoteFileStorage, _client=self.files))

    @property
    def Function(self) -> type[NotteFunction]:
        return cast(type[NotteFunction], partial(NotteFunction, _client=self))

    def health_check(self) -> None:
        """
        Health check the Notte API.
        """
        return self.sessions.health_check()

    # response_format provided, raise_on_failure=True (default) -> unwrapped TBaseModel
    @overload
    def scrape(  # pyright: ignore[reportOverlappingOverload]
        self,
        /,
        url: str,
        *,
        response_format: type[TBaseModel],
        instructions: str | None = None,
        raise_on_failure: Literal[True] = ...,
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> TBaseModel: ...

    # response_format provided, raise_on_failure=False -> wrapped StructuredData[TBaseModel]
    @overload
    def scrape(
        self,
        /,
        url: str,
        *,
        response_format: type[TBaseModel],
        instructions: str | None = None,
        raise_on_failure: Literal[False],
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> StructuredData[TBaseModel]: ...

    # instructions only, raise_on_failure=True (default) -> unwrapped BaseModel
    @overload
    def scrape(
        self,
        /,
        url: str,
        *,
        instructions: str,
        raise_on_failure: Literal[True] = ...,
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> dict[str, Any]: ...

    # instructions only, raise_on_failure=False -> wrapped StructuredData[BaseModel]
    @overload
    def scrape(
        self,
        /,
        url: str,
        *,
        instructions: str,
        raise_on_failure: Literal[False],
        **params: Unpack[ScrapeMarkdownParamsDict],
    ) -> StructuredData[BaseModel]: ...

    # markdown catch-all LAST: open Unpack[TypedDict] otherwise swallows every kwargs call under ty
    @overload
    def scrape(
        self, /, url: str, *, raise_on_failure: bool = True, **params: Unpack[ScrapeMarkdownParamsDict]
    ) -> str: ...

    def scrape(
        self, /, url: str, *, raise_on_failure: bool = True, **data: Unpack[ScrapeRequestDict]
    ) -> StructuredData[BaseModel] | BaseModel | dict[str, Any] | str:
        """
        Scrape the current page data.

        This endpoint is a wrapper around the `session.scrape` method that automatically starts a new session, goes to the given URL, and scrapes the page.

        **Example:**
        ```python
        from notte_sdk import NotteClient

        client = NotteClient()
        markdown = client.scrape("https://www.google.com", only_main_content=False)
        ```

        With structured data:
        ```python
        from notte_sdk import NotteClient
        from pydantic import BaseModel

        # Define your Pydantic model
        ...

        client = NotteClient()
        data = client.scrape(
            "https://www.notte.cc",
            response_format=Product,
            instructions="Extract the products names and prices"
        )
        ```

        Args:
            url: The URL to scrape.
            raise_on_failure: If True (default), raises ScrapeFailedError when structured data
                extraction fails and returns the extracted data directly. If False, returns
                the StructuredData wrapper so user can check .success.
            **data: Additional parameters for the scrape.

        Returns:
            When using instructions/response_format and raise_on_failure=True: returns the extracted data directly.
            When raise_on_failure=False: returns StructuredData wrapper so user can check .success.
            For markdown scraping: returns str.
        """
        with self.Session(open_viewer=False, perception_type="fast") as session:
            # best-effort navigation: scrape whatever loaded unless the goto
            # actually threw server side
            result = session.execute(GotoAction(url=url), raise_on_failure=False)
            if not result.success and result.exception is not None:
                raise result.exception
            return session.scrape(raise_on_failure=raise_on_failure, **data)


@final
class AsyncNotteClient:
    """
    Async client for the Notte API. Preview: the API resources only, for now.

    `sessions`, `functions`, `files`, `personas`, `profiles`, `vaults` and `managed_auth` have the
    same methods as on `NotteClient`, as coroutines, with the same arguments, results and
    exceptions, except `functions.get_curl` and `functions.decode_message`, which only format text
    and stay plain methods. So do `health_check` and the methods of the `Persona` and `Vault`
    objects that call the API (their methods without I/O, such as `generate_password()`, stay
    plain). `Function` and `FileStorage` create `AsyncNotteFunction` and `AsyncRemoteFileStorage`.
    Not yet available: the session methods the sync resources extend beyond the API call (for example
    `sessions.stop`, `sessions.replay`, the viewers and `sessions.page`), `scrape`,
    `AsyncNotteFunction.replay`, and the `Session` object. They will be added later.

    **Example:**
    ```python
    from notte_sdk import AsyncNotteClient

    async with AsyncNotteClient() as client:
        sessions = await client.sessions.list()
    ```

    Connections open on the first request and belong to the event loop that made it. Close them
    with `async with` or `await client.aclose()`: they cannot be closed when the client is
    garbage collected, which emits a `ResourceWarning` instead. Using the client from another
    event loop while the first one is still open raises `RuntimeError`.
    """

    def __init__(
        self,
        api_key: str | None = None,
        server_url: str | None = None,
        verbose: bool = False,
        viewer_type: SessionViewerType = SessionViewerType.BROWSER,
        captcha_timeout_seconds: float = 180,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        """Initialize an AsyncNotteClient instance; takes the same arguments as `NotteClient`.

        Args:
            api_key: Optional API key for authentication.
            viewer_type: Kept for the session viewers, which are not available on this client yet.
            captcha_timeout_seconds: Total CAPTCHA wait budget, separate from action and HTTP timeouts.
            max_retries: Retries for transient failures (502, 503, 504, 529, and connection errors),
                with exponential backoff and full jitter. ``Retry-After`` is honored. POST and PATCH
                requests are only retried when the API cannot have processed them (503, 529,
                connection refused), so they are never applied twice. Set to 0 to disable retries.
        """
        api_key = _validated_settings(api_key, server_url, captcha_timeout_seconds, max_retries)
        self.captcha_timeout_seconds: float = captcha_timeout_seconds
        self.max_retries: int = max_retries
        self._viewer_type: SessionViewerType = viewer_type
        # One connection pool for every resource client below.
        self._http: AsyncSharedHttpClient = AsyncSharedHttpClient()
        _ = weakref.finalize(self, self._http.warn_unclosed)
        self.sessions: AsyncSessionsOperations = AsyncSessionsOperations(
            root_client=self, base_endpoint_path="sessions", api_key=api_key, server_url=server_url, verbose=verbose
        )
        self.personas: AsyncPersonasClient = AsyncPersonasClient(
            root_client=self, api_key=api_key, server_url=server_url, verbose=verbose
        )
        self.vaults: AsyncVaultsClient = AsyncVaultsClient(
            root_client=self, api_key=api_key, server_url=server_url, verbose=verbose
        )
        self.profiles: AsyncProfilesOperations = AsyncProfilesOperations(
            root_client=self, api_key=api_key, server_url=server_url, verbose=verbose
        )
        self.managed_auth: AsyncManagedAuthClient = AsyncManagedAuthClient(
            root_client=self, api_key=api_key, server_url=server_url, verbose=verbose
        )
        self.files: AsyncFileStorageClient = AsyncFileStorageClient(
            root_client=self, api_key=api_key, server_url=server_url, verbose=verbose
        )
        self.functions: AsyncFunctionsClient = AsyncFunctionsClient(
            root_client=self, api_key=api_key, server_url=server_url, verbose=verbose
        )

        if self.sessions.server_url != self.sessions.DEFAULT_NOTTE_API_URL:
            logger.warning(f"NOTTE_API_URL is set to: {self.sessions.server_url}")

    async def aclose(self) -> None:
        """Close pooled HTTP connections. The client stays usable: a later request opens new ones."""
        await self._http.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    @property
    def Vault(self) -> type[AsyncNotteVault]:
        return cast(type[AsyncNotteVault], partial(AsyncNotteVault, _client=self.vaults))

    @property
    def Persona(self) -> type[AsyncNottePersona]:
        return cast(type[AsyncNottePersona], partial(AsyncNottePersona, _client=self))

    @property
    def FileStorage(self) -> type[AsyncRemoteFileStorage]:
        return cast(type[AsyncRemoteFileStorage], partial(AsyncRemoteFileStorage, _client=self.files))

    @property
    def Function(self) -> type[AsyncNotteFunction]:
        return cast(type[AsyncNotteFunction], partial(AsyncNotteFunction, _client=self))

    async def health_check(self) -> None:
        """
        Health check the Notte API.
        """
        return await self.sessions.health_check()
