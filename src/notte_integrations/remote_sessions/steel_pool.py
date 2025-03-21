import os

import requests
from loguru import logger
from pydantic import Field
from typing_extensions import override

from notte.browser.pool.base import BrowserResourceOptions, BrowserWithContexts
from notte.browser.pool.cdp_pool import BrowserEnum, CDPBrowserPool, CDPSession


def get_steel_api_key() -> str:
    steel_api_key: str | None = os.getenv("STEEL_API_KEY")
    if steel_api_key is None:
        raise ValueError("STEEL_API_KEY is not set")
    return steel_api_key


class SteelBrowserPool(CDPBrowserPool):
    steel_base_url: str = "api.steel.dev"  # localhost:3000"
    steel_api_key: str = Field(default_factory=get_steel_api_key)

    @property
    @override
    def browser_type(self) -> BrowserEnum:
        return BrowserEnum.CHROMIUM

    @override
    def create_session_cdp(self, resource_options: BrowserResourceOptions | None = None) -> CDPSession:
        logger.info("Creating Steel session...")

        url = f"https://{self.steel_base_url}/v1/sessions"

        headers = {"Steel-Api-Key": self.steel_api_key}

        response = requests.post(url, headers=headers)
        response.raise_for_status()
        data: dict[str, str] = response.json()
        if "localhost" in self.steel_base_url:
            cdp_url = f"ws://{self.steel_base_url}/v1/devtools/browser/{data['id']}"
        else:
            cdp_url = f"wss://connect.steel.dev?apiKey={self.steel_api_key}&sessionId={data['id']}"
        return CDPSession(session_id=data["id"], cdp_url=cdp_url)

    @override
    async def close_playwright_browser(self, browser: BrowserWithContexts, force: bool = True) -> bool:
        if self.config.verbose:
            logger.info(f"Closing CDP session for URL {browser.cdp_url}")
        steel_session = self.sessions[browser.browser_id]

        url = f"https://{self.steel_base_url}/v1/sessions/{steel_session.session_id}/release"

        headers = {"Steel-Api-Key": self.steel_api_key}

        response = requests.post(url, headers=headers)
        if response.status_code != 200:
            if self.config.verbose:
                logger.error(f"Failed to release Steel session {steel_session.session_id}: {response.json()}")
            return False
        del self.sessions[browser.browser_id]
        return True
