# @sniptest filename=quickstart.py
from notte_sdk import NotteClient

client = NotteClient()
markdown = client.scrape("https://example.com")
print(markdown)
