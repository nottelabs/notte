# @sniptest filename=steel_init.py
# @sniptest typecheck_only=true
import os

from notte_sdk import NotteClient
from steel import Steel

STEEL_API_KEY = os.getenv("STEEL_API_KEY")

# Initialize clients
steel = Steel(steel_api_key=STEEL_API_KEY)
client = NotteClient()

# Create a browser session on Steel
steel_session = steel.sessions.create()
