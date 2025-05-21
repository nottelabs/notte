from abc import ABC, abstractmethod

from loguru import logger
from notte_browser.playwright import WindowManager
from notte_browser.window import BrowserResource, BrowserWindowOptions
from notte_core.common.config import BrowserType
from patchright.async_api import Browser as PatchrightBrowser
from pydantic import BaseModel, Field
from typing_extensions import override


class CDPSession(BaseModel):
    session_id: str
    cdp_url: str
    resource: BrowserResource | None = None


class CDPSessionsManager(WindowManager, ABC):
    sessions: dict[str, CDPSession] = Field(default_factory=dict)
    last_session: CDPSession | None = Field(default=None)
    browser_type: BrowserType = Field(default=BrowserType.CHROMIUM)

    @abstractmethod
    def create_session_cdp(self) -> CDPSession:
        pass

    @abstractmethod
    def close_session_cdp(self, session_id: str) -> bool:
        pass

    @override
    async def create_playwright_browser(self, options: BrowserWindowOptions) -> PatchrightBrowser:
        session = self.create_session_cdp()
        if session.cdp_url in self.sessions:
            raise ValueError(f"Session {session.session_id} already exists")

        cdp_options = options.set_cdp_url(session.cdp_url)
        logger.info(f"Connecting to CDP at {cdp_options.cdp_url}")
        browser = await self.connect_cdp_browser(cdp_options)
        self.sessions[session.cdp_url] = session
        self.last_session = session
        return browser

    @override
    async def get_browser_resource(self, options: BrowserWindowOptions) -> BrowserResource:
        resource = await super().get_browser_resource(options)
        cdp_url = resource.options.cdp_url
        if cdp_url is None:
            if self.last_session is None:
                raise ValueError(f"CDP URL is not set for resource {cdp_url} and last session is not set")
            logger.info(f"Setting CDP URL for resource {cdp_url} to {self.last_session.cdp_url}")
            resource.options = resource.options.set_cdp_url(self.last_session.cdp_url)
            cdp_url = self.last_session.cdp_url
        if cdp_url not in self.sessions:
            raise ValueError(f"Session {cdp_url} not found")
        self.sessions[cdp_url].resource = resource
        self.browser = None  # pyright: ignore[reportUnannotatedClassAttribute]
        self.last_session = None
        return resource

    @override
    async def release_browser_resource(self, resource: BrowserResource) -> None:
        await super().release_browser_resource(resource)
        cdp_url = resource.options.cdp_url
        if cdp_url not in self.sessions:
            raise ValueError(f"Session {cdp_url} not found")
        session = self.sessions[cdp_url]
        status = self.close_session_cdp(session.session_id)
        if not status:
            logger.error(f"Failed to close session {session.session_id}")
        del self.sessions[cdp_url]

    @override
    async def stop(self) -> None:
        await super().stop()
        for session in self.sessions.values():
            _ = self.close_session_cdp(session.session_id)
