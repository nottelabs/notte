import os

from loguru import logger
from notte_browser.window import BrowserWindowOptions
from typing_extensions import override

from notte_integrations.sessions.cdp_session import CDPSession, CDPSessionsManager

try:
    from browserbase import Browserbase
except ImportError:
    raise ImportError("Install with notte[browserbase] to include browserbase integration")


# TODO: use api with requests instead of sdk so we don't have the added dependency
class BrowserBaseSessionsManager(CDPSessionsManager):
    def __init__(
        self,
        verbose: bool = False,
        stealth: bool = False,
    ):
        super().__init__()

        bb_api_key: str | None = os.getenv("BROWSERBASE_API_KEY")
        bb_project_id: str | None = os.getenv("BROWSERBASE_PROJECT_ID")

        if bb_api_key is None:
            raise ValueError("BROWSERBASE_API_KEY env variable is not set")

        if bb_project_id is None:
            raise ValueError("BROWSERBASE_PROJECT_ID env variable is not set")

        self.bb_api_key: str = bb_api_key
        self.bb_project_id: str = bb_project_id

        self.bb: Browserbase = Browserbase(api_key=self.bb_api_key)
        self.stealth: bool = stealth
        self.verbose: bool = verbose

    @override
    def create_session_cdp(self, options: BrowserWindowOptions) -> CDPSession:
        if self.verbose:
            logger.info("Creating BrowserBase session...")

        stealth_args = dict(
            browser_settings={
                "fingerprint": {
                    "browsers": ["chrome", "firefox", "edge", "safari"],
                    "devices": ["mobile", "desktop"],
                    "locales": ["en-US", "en-GB"],
                    "operatingSystems": ["android", "ios", "linux", "macos", "windows"],
                    "screen": {
                        "maxHeight": options.viewport_height or 1080,
                        "maxWidth": options.viewport_width or 1920,
                        "minHeight": options.viewport_height or 1080,
                        "minWidth": options.viewport_width or 1920,
                    },
                    "viewport": {
                        "width": options.viewport_width or 1920,
                        "height": options.viewport_height or 1080,
                    },
                },
                "solveCaptchas": True,
            },
            proxies=True if options.proxy is not None else False,
        )

        args = stealth_args if self.stealth else {}
        session = self.bb.sessions.create(project_id=self.bb_project_id, **args)  # type: ignore

        if self.verbose:
            logger.info(f"Got BrowserBase session {session}")

        return CDPSession(
            session_id=session.id,
            cdp_url=session.connect_url,
        )

    @override
    def close_session_cdp(self, session_id: str) -> bool:
        if self.verbose:
            logger.info(f"Closing CDP session for URL {session_id}")
        return True
