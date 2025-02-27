from abc import ABC, abstractmethod

from loguru import logger
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
