# @sniptest filename=link_placeholders.py
from notte_sdk import NotteClient

client = NotteClient()

# Use placeholders for links and images
markdown = client.scrape(url, use_link_placeholders=True)
