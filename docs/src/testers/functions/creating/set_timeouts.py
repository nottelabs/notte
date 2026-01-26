# @sniptest filename=set_timeouts.py
from notte_sdk import NotteClient


def run(url: str):
    client = NotteClient()

    # Set session timeout
    with client.Session(idle_timeout_minutes=5) as session:
        session.execute(type="goto", url=url)
        data = session.scrape()

    return data
