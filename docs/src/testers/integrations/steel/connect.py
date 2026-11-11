# @sniptest filename=steel_connect.py
# @sniptest show=11-17
# @sniptest typecheck_only=true
import os

from notte_sdk import NotteClient
from steel import Steel

STEEL_API_KEY = os.getenv("STEEL_API_KEY")
steel = Steel(steel_api_key=STEEL_API_KEY)
client = NotteClient()
steel_session = steel.sessions.create()

# Connect Notte to Steel's browser via CDP. Steel's URL needs your API key.
with client.Session(cdp_url=f"{steel_session.websocket_url}&apiKey={STEEL_API_KEY}") as session:
    # Drive the Steel browser with Notte actions
    session.execute(type="goto", url="https://www.notte.cc/pricing")

    # Extract structured data from the page
    pricing = session.scrape(instructions="extract the pricing plans")
