# @sniptest filename=connect_url.py
# @sniptest show=9-27
# ruff: noqa: E402 -- hidden live fixture precedes displayed imports
import os

api_key = os.environ["NOTTE_API_KEY"]
connect_url = (
    os.environ.get("NOTTE_API_URL", "https://api.notte.cc").replace("https://", "wss://") + "/sessions/connect"
)

from urllib.parse import urlencode

from patchright.sync_api import sync_playwright

# connect_url is "wss://api.notte.cc/sessions/connect"
# Pass your API key and session options in the query string
query = urlencode({"token": api_key, "proxies": "false", "max_duration_minutes": 10})
url = f"{connect_url}?{query}"

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
