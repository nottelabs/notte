# @sniptest filename=quick_scrape.py
from notte_sdk import NotteClient

client = NotteClient()

# Returns markdown content
markdown = client.scrape("https://example.com")
