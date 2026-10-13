# @sniptest filename=timeout_example.py
# @sniptest show=5-7
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(idle_timeout_minutes=15) as session:
    # Complex automation
    pass

    # Values retained for the external test runner, outside the displayed range.
    status = session.status()
