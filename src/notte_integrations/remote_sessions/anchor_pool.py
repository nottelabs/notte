import os

import requests
from loguru import logger
from typing_extensions import override

from notte.browser.pool.base import BrowserWithContexts
from notte.browser.pool.cdp_pool import CDPBrowserPool, CDPSession


class AnchorBrowserPool(CDPBrowserPool):
    def __init__(
        self,
        anchor_base_url: str = "https://api.anchorbrowser.io",
        verbose: bool = False,
    ):
        super().__init__(verbose=verbose)
        self.anchor_api_key: str | None = os.getenv("ANCHOR_API_KEY")
        if self.anchor_api_key is None:
            raise ValueError("ANCHOR_API_KEY is not set")
        self.anchor_base_url: str = anchor_base_url

    @override
    def create_session_cdp(self) -> CDPSession:
        if self.verbose:
            logger.info("Creating Anchor session...")
        browser_configuration = None
        response = requests.post(
            f"{self.anchor_base_url}/api/sessions",
            headers={
                "anchor-api-key": self.anchor_api_key,
                "Content-Type": "application/json",
            },
            json=browser_configuration,
        )
        response.raise_for_status()
        session_id: str = response.json()["id"]
        return CDPSession(
            session_id=session_id,
            cdp_url=f"wss://connect.anchorbrowser.io?apiKey={self.anchor_api_key}&sessionId={session_id}",
        )

    @override
    async def close_playwright_browser(self, browser: BrowserWithContexts, force: bool = True) -> bool:
        if self.verbose:
            logger.info(f"Closing CDP session for URL {browser.cdp_url}")
        await browser.browser.close()
        del self.sessions[browser.browser_id]
        return True
