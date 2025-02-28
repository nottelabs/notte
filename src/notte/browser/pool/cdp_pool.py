from abc import ABC, abstractmethod

from loguru import logger
from patchright.async_api import Browser
from pydantic import BaseModel
from typing_extensions import override

from notte.browser.pool.base import BaseBrowserPool, BrowserWithContexts


class CDPSession(BaseModel):
    session_id: str
    cdp_url: str


class CDPBrowserPool(BaseBrowserPool, ABC):
    def __init__(self, verbose: bool = False):
        # TODO: check if contexts_per_browser should be set to 1
        super().__init__(contexts_per_browser=4, verbose=verbose)
        self.sessions: dict[str, CDPSession] = {}
        self.last_session: CDPSession | None = None

    @abstractmethod
    def create_session_cdp(self) -> CDPSession:
        pass

    @override
    async def create_playwright_browser(self, headless: bool) -> Browser:
        cdp_session = self.create_session_cdp()
        self.last_session = cdp_session
        return await self.playwright.chromium.connect_over_cdp(cdp_session.cdp_url)

    @override
    async def create_browser(self, headless: bool) -> BrowserWithContexts:
        browser = await super().create_browser(headless)
        if self.last_session is None:
            raise ValueError("Last session is not set")
        self.sessions[browser.browser_id] = self.last_session
        return browser


class SingleCDPBrowserPool(CDPBrowserPool):
    def __init__(self, cdp_url: str, verbose: bool = False):
        super().__init__(verbose)
        self.cdp_url: str | None = cdp_url

    @override
    def create_session_cdp(self) -> CDPSession:
        if self.cdp_url is None:
            raise ValueError("CDP URL is not set")
        return CDPSession(session_id=self.cdp_url, cdp_url=self.cdp_url)

    @override
    async def close_playwright_browser(self, browser: BrowserWithContexts, force: bool = True) -> bool:
        if self.verbose:
            logger.info(f"Closing CDP session for URL {browser.cdp_url}")
        self.cdp_url = None
        del self.sessions[browser.browser_id]
        return True
