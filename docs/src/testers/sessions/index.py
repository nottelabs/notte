# @sniptest filename=session.py
from notte_sdk import NotteClient

client = NotteClient()

# The session is automatically stopped when the context manager is exited
with client.Session(idle_timeout_minutes=2) as session:
    status = session.status()
    print(status)
