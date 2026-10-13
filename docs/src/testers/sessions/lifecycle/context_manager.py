# @sniptest filename=context_manager.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(idle_timeout_minutes=2) as session:
    print(session.session_id)
# Automatically stopped here
