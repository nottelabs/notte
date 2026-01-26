# @sniptest filename=link_placeholders.py
# @sniptest show=6-8
from notte_sdk import NotteClient

client = NotteClient()
url = "https://example.com"

# Use placeholders for links and images
markdown = client.scrape(url, use_link_placeholders=True)
