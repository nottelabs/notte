from abc import ABC, abstractmethod
from enum import StrEnum

from loguru import logger
from patchright.async_api import Browser as PatchrightBrowser
from patchright.async_api import ProxySettings
from pydantic import BaseModel
from typing_extensions import override

from notte.browser.pool.base import BaseBrowserPool, BrowserWithContexts


class CDPSession(BaseModel):
    session_id: str
    cdp_url: str


class BrowserEnum(StrEnum):
    CHROMIUM = "chromium"
    FIREFOX = "firefox"


class CDPBrowserPool(BaseBrowserPool, ABC):
    def __init__(self, verbose: bool = False):
        # TODO: check if contexts_per_browser should be set to 1
        super().__init__(contexts_per_browser=4, verbose=verbose)
        self.sessions: dict[str, CDPSession] = {}
        self.last_session: CDPSession | None = None

    @property
    @abstractmethod
    def browser_type(self) -> BrowserEnum:
        pass

    @abstractmethod
    def create_session_cdp(self, proxy: ProxySettings | None = None) -> CDPSession:
        pass

    @override
    async def create_playwright_browser(self, headless: bool, proxy: ProxySettings | None = None) -> PatchrightBrowser:
        cdp_session = self.create_session_cdp(proxy=proxy)
        self.last_session = cdp_session

        # TODO: chromium doesn't need to use cdp, might want to clarify this
        match self.browser_type:
            case BrowserEnum.CHROMIUM:
                return await self.playwright.chromium.connect_over_cdp(cdp_session.cdp_url)
            case BrowserEnum.FIREFOX:
                return await self.playwright.firefox.connect(cdp_session.cdp_url)

    @override
    async def create_browser(self, headless: bool, proxy: ProxySettings | None = None) -> BrowserWithContexts:
        browser = await super().create_browser(headless, proxy)
        if self.last_session is None:
            raise ValueError("Last session is not set")
        self.sessions[browser.browser_id] = self.last_session
        return browser


class SingleCDPBrowserPool(CDPBrowserPool):
    def __init__(self, cdp_url: str, verbose: bool = False):
        super().__init__(verbose)
        self.cdp_url: str | None = cdp_url

    @property
    @override
    def browser_type(self) -> BrowserEnum:
        return BrowserEnum.CHROMIUM

    @override
    def create_session_cdp(self, proxy: ProxySettings | None = None) -> CDPSession:
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
