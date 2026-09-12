# @sniptest filename=links_and_images.py
# @sniptest show=6-16
from notte_sdk import NotteClient

client = NotteClient()
url = "https://example.com"

# Include links (default)
markdown = client.scrape(url, scrape_links=True)

# Exclude links
markdown = client.scrape(url, scrape_links=False)

# Include images in markdown
markdown = client.scrape(url, scrape_images=True)

# Exclude images (default)
markdown = client.scrape(url, scrape_images=False)

# Preserve the displayed overwrite pattern; retain separate responses for option checks.
with_links = client.scrape(url, scrape_links=True)
without_links = client.scrape(url, scrape_links=False)
results = [
    isinstance(markdown, str),
    "Example Domain" in markdown,
    "[Learn more](https://iana.org/domains/example)" in with_links,
    "Learn more" in without_links and "iana.org" not in without_links,
]
