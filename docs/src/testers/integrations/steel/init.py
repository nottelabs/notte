# @sniptest filename=steel_init.py
# @sniptest show=19-26
import os

from notte_sdk import NotteClient


class SteelSession:
    websocket_url: str = "wss://connect.steel.dev/session"


class Sessions:
    def create(self) -> "SteelSession":
        return SteelSession()


class Steel:
    def __init__(self, steel_api_key: str | None = None):
        self.sessions = Sessions()


STEEL_API_KEY = os.getenv("STEEL_API_KEY")

# Initialize clients
steel = Steel(steel_api_key=STEEL_API_KEY)
client = NotteClient()

# Create a browser session on Steel
steel_session = steel.sessions.create()
