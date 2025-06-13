import os

from loguru import logger
from notte_browser.window import BrowserWindowOptions
from notte_sdk.client import NotteClient
from typing_extensions import override

from notte_integrations.sessions.cdp_session import CDPSession, CDPSessionsManager


class NotteSessionsManager(CDPSessionsManager):
    def __init__(self):
        super().__init__()

        notte_api_key: str | None = os.getenv("NOTTE_API_KEY")

        if notte_api_key is None:
            raise ValueError("NOTTE_API_KEY env variable is not set")

        self.notte: NotteClient = NotteClient(api_key=notte_api_key)

    @override
    def create_session_cdp(self, options: BrowserWindowOptions) -> CDPSession:
        logger.info("Creating Notte session...")

        session = self.notte.Session(
            headless=options.headless,
            viewport_width=options.viewport_width,
            viewport_height=options.viewport_height,
            proxies=options.proxy is not None,
        )
        session.start()
        if self.verbose:
            logger.info(f"Got Notte session {session}")

        debug_info = session.debug_info()
        logger.info(f"Notte session debug info: {debug_info}")

        return CDPSession(
            session_id=session.session_id,
            cdp_url=session.cdp_url(),
        )

    @override
    def close_session_cdp(self, session_id: str) -> bool:
        if self.verbose:
            logger.info(f"Closing CDP session {session_id}")

        try:
            _ = self.notte.sessions._stop(session_id)  # pyright: ignore[reportPrivateUsage]
            return True
        except Exception as e:
            logger.error(f"Error closing session: {e}")
            return False
