# @sniptest filename=steel_complete.py
# @sniptest typecheck_only=true
import os

from notte_sdk import NotteClient
from steel import Steel

STEEL_API_KEY = os.getenv("STEEL_API_KEY")

steel = Steel(steel_api_key=STEEL_API_KEY)
client = NotteClient()

# Create a browser session on Steel
steel_session = steel.sessions.create()

try:
    # Connect Notte to Steel's browser via CDP. Steel's URL needs your API key.
    with client.Session(cdp_url=f"{steel_session.websocket_url}&apiKey={STEEL_API_KEY}") as session:
        session.execute(type="goto", url="https://www.notte.cc/pricing")

        pricing = session.scrape(instructions="extract the pricing plans")

        print(f"Pricing: {pricing}")

except Exception as e:
    print(f"Error during automation: {e}")

finally:
    steel.sessions.release(steel_session.id)
    print("Steel session released")
