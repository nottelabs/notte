# @sniptest filename=basic_function.py
from notte_sdk import NotteClient

client = NotteClient()


def run(url: str, search_query: str):
    """Search a website url and extract results."""

    with client.Session() as session:
        # Navigate to site
        session.execute(type="goto", url=url)

        # Search
        session.execute(type="fill", selector="input[name='search']", value=search_query)
        session.execute(type="press_key", key="Enter")

        # Extract results
        results = session.scrape(instructions="Extract search results")

        return results
