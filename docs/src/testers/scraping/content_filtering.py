# @sniptest filename=content_filtering.py
# @sniptest show=6-10
from notte_sdk import NotteClient

client = NotteClient()
url = "https://example.com"

# Include all page content (default)
markdown = client.scrape(url, only_main_content=False)

# Only main content (excludes navbars, footers, sidebars)
markdown = client.scrape(url, only_main_content=True)

results = [isinstance(markdown, str), "Example Domain" in markdown]
