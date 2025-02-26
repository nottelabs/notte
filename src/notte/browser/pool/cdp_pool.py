from abc import ABC, abstractmethod
from typing_extensions import override
from loguru import logger
from patchright.async_api import Browser as PatchrightBrowser
from pydantic import BaseModel, Field
from typing_extensions import override

from notte.browser.pool.base import BaseBrowserPool, BrowserResource, BrowserWithContexts


class CDPSession(BaseModel):
    session_id: str
    cdp_url: str


class CDPBrowserPool(BaseBrowserPool, ABC):
    sessions: dict[str, CDPSession] = Field(default_factory=dict)
    last_session: CDPSession | None = Field(default=None)

    @abstractmethod
    def create_session_cdp(self) -> CDPSession:
        pass

    @override
    async def create_playwright_browser(self, headless: bool, port: int | None) -> PatchrightBrowser:
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
    cdp_url: str | None = None

    @override
    def create_session_cdp(self) -> CDPSession:
        if self.cdp_url is None:
            raise ValueError("CDP URL is not set")
        return CDPSession(session_id=self.cdp_url, cdp_url=self.cdp_url)

    @override
    async def get_browser_resource(self, headless: bool) -> BrowserResource:
        # start the pool automatically for single browser pool
        await self.start()
        return await super().get_browser_resource(headless)

    @override
    async def close_playwright_browser(self, browser: BrowserWithContexts, force: bool = True) -> bool:
        if self.config.verbose:
            logger.info(f"Closing CDP session for URL {browser.cdp_url}")
        self.cdp_url = None
        del self.sessions[browser.browser_id]
        await self.stop()
        return True
