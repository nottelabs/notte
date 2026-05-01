# @sniptest filename=content_monitoring.py
from notte_sdk import NotteClient

client = NotteClient()

# Get current content
content = client.scrape("https://example.com/pricing", instructions="Extract all pricing tiers and their features")

# Compare with previous version
# ...
