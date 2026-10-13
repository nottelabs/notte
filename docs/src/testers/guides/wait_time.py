# @sniptest filename=wait_time.py
# @sniptest show=1-7
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # Wait 2 seconds before continuing
    session.execute(type="wait", time_ms=2000)

status = session.status()
