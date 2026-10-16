# @sniptest filename=steel_complete.py
# @sniptest show=23-47
# @sniptest typecheck_only=true
import os

from notte_sdk import NotteClient


class SteelSession:
    websocket_url: str = "wss://connect.steel.dev/session"
    id: str = "session_123"


class Sessions:
    def create(self) -> "SteelSession":
        return SteelSession()

    def release(self, session_id: str) -> None:
        pass


class Steel:
    def __init__(self, steel_api_key: str | None = None):
        self.sessions = Sessions()


STEEL_API_KEY = os.getenv("STEEL_API_KEY")

steel = Steel(steel_api_key=STEEL_API_KEY)
client = NotteClient()

# Create a browser session on Steel
steel_session = steel.sessions.create()

try:
    # Connect Notte to Steel's browser via CDP
    with client.Session(cdp_url=steel_session.websocket_url) as session:
        session.execute(type="goto", url="https://www.notte.cc/pricing")

        pricing = session.scrape(instructions="extract the pricing plans")

        print(f"Pricing: {pricing}")

except Exception as e:
    print(f"Error during automation: {e}")

finally:
    steel.sessions.release(steel_session.id)
    print("Steel session released")
