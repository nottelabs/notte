from abc import ABC, abstractmethod
from enum import StrEnum

from loguru import logger
from patchright.async_api import Browser as PatchrightBrowser
from pydantic import BaseModel, Field
from typing_extensions import override

from notte.browser.pool.base import (
    BaseBrowserPool,
    BrowserResource,
    BrowserResourceOptions,
    BrowserWithContexts,
)


class CDPSession(BaseModel):
    session_id: str
    cdp_url: str


class BrowserEnum(StrEnum):
    CHROMIUM = "chromium"
    FIREFOX = "firefox"


class CDPBrowserPool(BaseBrowserPool, ABC):
    sessions: dict[str, CDPSession] = Field(default_factory=dict)
    last_session: CDPSession | None = Field(default=None)

    @property
    @abstractmethod
    def browser_type(self) -> BrowserEnum:
        pass

    @abstractmethod
    def create_session_cdp(self, resource_options: BrowserResourceOptions | None = None) -> CDPSession:
        pass

    @override
    async def create_playwright_browser(self, resource_options: BrowserResourceOptions) -> PatchrightBrowser:
        cdp_session = self.create_session_cdp(resource_options)
        self.last_session = cdp_session

        match self.browser_type:
            case BrowserEnum.CHROMIUM:
                return await self.playwright.chromium.connect_over_cdp(cdp_session.cdp_url)
            case BrowserEnum.FIREFOX:
                return await self.playwright.firefox.connect(cdp_session.cdp_url)

    @override
    async def create_browser(self, resource_options: BrowserResourceOptions) -> BrowserWithContexts:
        browser = await super().create_browser(resource_options)
        if self.last_session is None:
            raise ValueError("Last session is not set")
        self.sessions[browser.browser_id] = self.last_session
        return browser


class SingleCDPBrowserPool(CDPBrowserPool):
    cdp_url: str | None = None

    @property
    @override
    def browser_type(self) -> BrowserEnum:
        return BrowserEnum.CHROMIUM

    @override
    def create_session_cdp(self, resource_options: BrowserResourceOptions | None = None) -> CDPSession:
        if self.cdp_url is None:
            raise ValueError("CDP URL is not set")
        return CDPSession(session_id=self.cdp_url, cdp_url=self.cdp_url)

    @override
    async def get_browser_resource(self, resource_options: BrowserResourceOptions) -> BrowserResource:
        # start the pool automatically for single browser pool
        await self.start()
        return await super().get_browser_resource(resource_options)

    @override
    async def close_playwright_browser(self, browser: BrowserWithContexts, force: bool = True) -> bool:
        if self.config.verbose:
            logger.info(f"Closing CDP session for URL {browser.cdp_url}")
        self.cdp_url = None
        del self.sessions[browser.browser_id]
        await self.stop()
        return True
