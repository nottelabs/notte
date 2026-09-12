# @sniptest filename=wait.py
# @sniptest show=1-12
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    session.execute(type="goto", url="https://example.com")

    # Wait 2 seconds
    session.execute(type="wait", time_ms=2000)

    # Wait 5 seconds for page to load
    session.execute(type="wait", time_ms=5000)

status = session.status()
