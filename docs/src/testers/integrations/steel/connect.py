# @sniptest filename=steel_connect.py
# @sniptest show=23-31
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


steel = Steel(steel_api_key=os.getenv("STEEL_API_KEY"))
client = NotteClient()
steel_session = steel.sessions.create()

# Connect Notte to Steel's browser via CDP
with client.Session(cdp_url=steel_session.websocket_url) as session:
    # Create an agent with a task
    agent = client.Agent(session=session, max_steps=10)

    # Run your automation task
    result = agent.run(task="extract pricing plans from https://www.notte.cc")
