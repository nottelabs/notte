# pyright: reportImportCycles=false
import math
import os
from functools import partial
from typing import Any, Literal, Unpack, cast, overload

from notte_core import enable_nest_asyncio
from notte_core.actions import GotoAction
from notte_core.data import StructuredData, TBaseModel
from notte_core.logging import logger
from notte_core.types import ScrapeMarkdownParamsDict, ScrapeRequestDict
from pydantic import BaseModel
from typing_extensions import final

from notte_sdk._retry import DEFAULT_MAX_RETRIES
from notte_sdk.auth import MISSING_API_KEY_MESSAGE, resolve_api_key
from notte_sdk.endpoints.base import BaseClient
from notte_sdk.endpoints.files import FileStorageClient, RemoteFileStorage
from notte_sdk.endpoints.functions import FunctionsClient, NotteFunction
from notte_sdk.endpoints.managed_auth import ManagedAuthClient
from notte_sdk.endpoints.personas import NottePersona, PersonasClient
from notte_sdk.endpoints.profiles import ProfilesClient
from notte_sdk.endpoints.sessions import RemoteSession, SessionsClient, SessionViewerType
from notte_sdk.endpoints.vaults import NotteVault, VaultsClient
from notte_sdk.errors import AuthenticationError

enable_nest_asyncio()


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

        if not math.isfinite(captcha_timeout_seconds) or captcha_timeout_seconds <= 0:
            raise ValueError("captcha_timeout_seconds must be finite and greater than zero")
        self.captcha_timeout_seconds: float = captcha_timeout_seconds
        if type(max_retries) is not int or max_retries < 0:
            raise ValueError("max_retries must be a non-negative integer")
        self.max_retries: int = max_retries
        # Resolve once so the keyring is read at most once per client.
        api_key = resolve_api_key(api_key, server_url or os.getenv("NOTTE_API_URL") or BaseClient.DEFAULT_NOTTE_API_URL)
        if api_key is None:
            raise AuthenticationError(MISSING_API_KEY_MESSAGE)
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
