import os

import requests
from loguru import logger
from notte_browser.window import BrowserWindowOptions
from pydantic import Field
from typing_extensions import override

from notte_integrations.sessions.cdp_session import CDPSession, CDPSessionsManager


def get_steel_api_key() -> str:
    steel_api_key: str | None = os.getenv("STEEL_API_KEY")
    if steel_api_key is None:
        raise ValueError("STEEL_API_KEY is not set")
    return steel_api_key


class SteelSessionsManager(CDPSessionsManager):
    steel_base_url: str = "api.steel.dev"  # localhost:3000"
    steel_api_key: str = Field(default_factory=get_steel_api_key)
    region: str = "fra"

    @override
    def create_session_cdp(self, options: BrowserWindowOptions) -> CDPSession:
        logger.info("Creating Steel session...")

        url = f"https://{self.steel_base_url}/v1/sessions"

        headers = {"Steel-Api-Key": self.steel_api_key}

        response = requests.post(url, headers=headers, json={"region": self.region})
        response.raise_for_status()
        data: dict[str, str] = response.json()
        if "localhost" in self.steel_base_url:
            cdp_url = f"ws://{self.steel_base_url}/v1/devtools/browser/{data['id']}"
        else:
            cdp_url = f"wss://connect.steel.dev?apiKey={self.steel_api_key}&sessionId={data['id']}"
        return CDPSession(session_id=data["id"], cdp_url=cdp_url)

    @override
    def close_session_cdp(self, session_id: str) -> bool:
        if self.verbose:
            logger.info(f"Closing CDP session for URL {session_id}")

        url = f"https://{self.steel_base_url}/v1/sessions/{session_id}/release"

        headers = {"Steel-Api-Key": self.steel_api_key}

        response = requests.post(url, headers=headers)
        if response.status_code != 200:
            if self.verbose:
                logger.error(f"Failed to release Steel session {session_id}: {response.json()}")
            return False
        return True
