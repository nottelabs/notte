# @sniptest filename=connect_url.py
# @sniptest show=1-20
import os
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright

# Pass your API key and session options in the query string
query = urlencode({"token": os.environ["NOTTE_API_KEY"], "proxies": "false", "max_duration_minutes": 10})
api_url = os.environ.get("NOTTE_API_URL", "https://api.notte.cc").rstrip("/")
url = f"{api_url.replace('https://', 'wss://')}/sessions/connect?{query}"

with sync_playwright() as p:
    # Connecting starts a new Notte session
    browser = p.chromium.connect_over_cdp(url)
    try:
        page = browser.contexts[0].pages[0]
        _ = page.goto("https://example.com")
        title = page.title()
    finally:
        # Closing the connection stops the session
        browser.close()

results = [title]
