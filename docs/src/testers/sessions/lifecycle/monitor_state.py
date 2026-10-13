# @sniptest filename=monitor_state.py
# @sniptest show=5-11
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    status = session.status()
    if status.status != "active":
        raise Exception("Session is no longer active")

    # Continue with operations
    pass

    # Values retained for the external test runner, outside the displayed range.
    status = session.status()
