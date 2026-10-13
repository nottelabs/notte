import os

from notte_sdk import NotteClient
from playwright.sync_api import sync_playwright

client = NotteClient()

with client.Session(idle_timeout_minutes=2) as session:
    cdp_url = session.cdp_url()

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_url)
        try:
            page = browser.contexts[0].pages[0]
            page.goto("https://www.google.com")
            page.screenshot(path=os.environ.get("NOTTE_SCREENSHOT_PATH", "screenshot.png"))
        finally:
            browser.close()
