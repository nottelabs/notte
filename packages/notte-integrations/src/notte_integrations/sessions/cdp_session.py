from abc import ABC, abstractmethod

from loguru import logger
from notte_browser.playwright import PlaywrightManager
from notte_browser.playwright_async_api import Browser
from notte_browser.window import BrowserResource, BrowserWindowOptions
from notte_core.common.config import BrowserType
from pydantic import BaseModel, Field
from typing_extensions import override


class CDPSession(BaseModel):
    session_id: str
    cdp_url: str
    resource: BrowserResource | None = None


class CDPSessionManager(PlaywrightManager, ABC):
    session: CDPSession | None = Field(default=None)
    browser_type: BrowserType = Field(default=BrowserType.CHROMIUM)

    @abstractmethod
    def create_session_cdp(self, options: BrowserWindowOptions) -> CDPSession:
        pass

    @abstractmethod
    def close_session_cdp(self, session_id: str) -> bool:
        pass

    @override
    async def create_playwright_browser(self, options: BrowserWindowOptions) -> Browser:
        self.session = self.create_session_cdp(options)
        cdp_options = options.set_cdp_url(self.session.cdp_url)
        logger.info(f"Connecting to CDP at {cdp_options.cdp_url}")
        browser = await self.connect_cdp_browser(cdp_options)
        return browser

    @override
    async def astop(self) -> None:
        await super().astop()
        if self.session is not None:
            _ = self.close_session_cdp(self.session.session_id)
