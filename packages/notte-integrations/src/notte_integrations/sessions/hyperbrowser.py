import asyncio
import os

from loguru import logger
from notte_browser.window import BrowserWindowOptions
from typing_extensions import override

from notte_integrations.sessions.cdp_session import CDPSession, CDPSessionManager

try:
    from hyperbrowser import AsyncHyperbrowser  # type: ignore
    from hyperbrowser.models import CreateSessionParams  # type: ignore
except ImportError:
    raise ImportError("Install with notte[hyperbrowser] to include hyperbrowser integration")


class HyperBrowserSessionsManager(CDPSessionManager):
    def __init__(
        self,
        verbose: bool = False,
        stealth: bool = False,
    ):
        super().__init__()

        hb_api_key: str | None = os.getenv("HYPERBROWSER_API_KEY")

        if hb_api_key is None:
            raise ValueError("HYPERBROWSER_API_KEY env variable is not set")

        self.hb_api_key: str = hb_api_key
        self.hb_client: AsyncHyperbrowser = AsyncHyperbrowser(api_key=self.hb_api_key)
        self.stealth: bool = stealth
        self.verbose: bool = verbose

    @override
    def create_session_cdp(self, options: BrowserWindowOptions) -> CDPSession:
        if self.verbose:
            logger.info("Creating HyperBrowser session...")

        session_params = CreateSessionParams(use_stealth=self.stealth)

        session = asyncio.run(self.hb_client.sessions.create(params=session_params))

        if self.verbose:
            logger.info(f"Got HyperBrowser session {session}")

        if session.ws_endpoint is None:
            raise ValueError("HyperBrowser session has no websocket endpoint")

        return CDPSession(
            session_id=session.id,
            cdp_url=session.ws_endpoint,
        )

    @override
    def close_session_cdp(self, session_id: str) -> bool:
        if self.verbose:
            logger.info(f"Closing CDP session {session_id}")

        try:
            _ = asyncio.run(self.hb_client.sessions.stop(session_id))
            return True
        except Exception as e:
            logger.error(f"Error closing session: {e}")
            return False
