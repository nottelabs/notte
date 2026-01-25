# @sniptest filename=wait_time.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # Wait 2 seconds before continuing
    session.execute(type="wait", time_ms=2000)
