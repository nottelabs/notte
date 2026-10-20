# @sniptest filename=links_and_images.py
# @sniptest show=6-10
from notte_sdk import NotteClient

client = NotteClient()
url = "https://example.com"

# Include links (default)
markdown = client.scrape(url, scrape_links=True)

# Exclude links
markdown = client.scrape(url, scrape_links=False)

# Preserve the displayed overwrite pattern; retain separate responses for option checks.
with_links = client.scrape(url, scrape_links=True)
without_links = client.scrape(url, scrape_links=False)
results = [
    isinstance(markdown, str),
    "Example Domain" in markdown,
    "[Learn more](https://iana.org/help/example-domains)" in with_links,
    "Learn more" in without_links and "iana.org" not in without_links,
]
