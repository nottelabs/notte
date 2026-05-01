# @sniptest filename=timeout_example.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(idle_timeout_minutes=15) as session:
    # Complex automation
    pass
