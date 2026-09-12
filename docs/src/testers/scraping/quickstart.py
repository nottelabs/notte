# @sniptest filename=quickstart.py
# @sniptest show=1-5
from notte_sdk import NotteClient

client = NotteClient()
markdown = client.scrape("https://example.com")
print(markdown)

results = [isinstance(markdown, str), "Example Domain" in markdown]
