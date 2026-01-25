# @sniptest filename=scoped_scraping.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # Scrape content within a specific selector
    content = session.scrape(selector="article.main-content")

    # Scrape a specific container
    content = session.scrape(selector="#product-details")
