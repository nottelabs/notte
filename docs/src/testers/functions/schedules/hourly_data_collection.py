# @sniptest filename=data_collector.py
from datetime import datetime

from notte_sdk import NotteClient


def run(source_url: str):
    """Collect data every hour."""
    client = NotteClient()

    with client.Session() as session:
        session.execute(type="goto", url=source_url)
        data = session.scrape()

    return {"data": data, "timestamp": datetime.now().isoformat()}
