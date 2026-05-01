# @sniptest filename=scraper_function.py
from notte_sdk import NotteClient


def run(url: str, selector: str):
    """
    Scrape data from a website.

    Args:
        url: The website URL
        selector: CSS selector for target element

    Returns:
        Extracted data
    """
    client = NotteClient()

    with client.Session() as session:
        session.execute(type="goto", url=url)
        data = session.scrape(instructions=f"Extract content from {selector}")

    return {"url": url, "data": data}
