# @sniptest filename=quick_scrape.py
# @sniptest show=1-6
from notte_sdk import NotteClient

client = NotteClient()

# Returns markdown content
markdown = client.scrape("https://example.com")

results = [isinstance(markdown, str), "Example Domain" in markdown]
