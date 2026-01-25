# @sniptest filename=monitor_state.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    status = session.status()
    if status.status != "active":
        raise Exception("Session is no longer active")

    # Continue with operations
    pass
