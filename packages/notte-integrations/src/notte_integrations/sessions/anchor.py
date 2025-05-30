import os
from typing import Any

import requests
from loguru import logger
from notte_browser.window import BrowserWindowOptions
from pydantic import Field
from typing_extensions import override

from notte_integrations.sessions.cdp_session import CDPSession, CDPSessionsManager


def get_anchor_api_key() -> str:
    anchor_api_key: str | None = os.getenv("ANCHOR_API_KEY")
    if anchor_api_key is None:
        raise ValueError("ANCHOR_API_KEY is not set")
    return anchor_api_key


class AnchorSessionsManager(CDPSessionsManager):
    anchor_base_url: str = "https://api.anchorbrowser.io"
    solve_captcha: bool = True
    anchor_api_key: str = Field(default_factory=get_anchor_api_key)

    @override
    def create_session_cdp(self, options: BrowserWindowOptions) -> CDPSession:
        if self.verbose:
            logger.info("Creating Anchor session...")

        browser_configuration: dict[str, Any] = {}

        if options.proxy is not None:
            browser_configuration["proxy_config"] = {"type": "anchor-residential", "active": True}

        if self.solve_captcha:
            browser_configuration["captcha_config"] = {"active": True}

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
    def close_session_cdp(self, session_id: str) -> bool:
        if self.verbose:
            logger.info(f"Closing CDP session for URL {session_id}")
        return True
