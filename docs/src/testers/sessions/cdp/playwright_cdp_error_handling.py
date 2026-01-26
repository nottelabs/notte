# @sniptest filename=playwright_cdp_error_handling.py
from notte_sdk import NotteClient
from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]

client = NotteClient()

with client.Session() as session:
    cdp_url = session.cdp_url()
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(cdp_url)
            # ... operations
        except Exception as e:
            print(f"CDP connection failed: {e}")
