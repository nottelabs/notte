# @sniptest filename=links_and_images.py
# @sniptest show=6-17
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
