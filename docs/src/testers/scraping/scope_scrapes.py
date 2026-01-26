# @sniptest filename=scope_scrapes.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session() as session:
    # Scrape only the main article, not comments or sidebar
    content = session.scrape(selector="article.main")
