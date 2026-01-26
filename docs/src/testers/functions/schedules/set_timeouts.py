# @sniptest filename=set_timeouts.py
from notte_sdk import NotteClient


def run():
    client = NotteClient()

    # Set timeout appropriate for schedule
    with client.Session(idle_timeout_minutes=10) as session:
        # Your automation
        pass
