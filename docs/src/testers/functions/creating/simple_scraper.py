# @sniptest filename=simple_scraper.py
from notte_sdk import NotteClient


def run(url: str):
    """Scrape page content."""
    client = NotteClient()

    with client.Session() as session:
        session.execute(type="goto", url=url)
        content = session.scrape()

    return content
