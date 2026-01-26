# @sniptest filename=cdp_playwright.py
from notte_sdk import NotteClient
from patchright.sync_api import sync_playwright

client = NotteClient()
with client.Session(proxies=False) as session:
    # get cdp url
    cdp_url = session.cdp_url()
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(cdp_url)
        page = browser.contexts[0].pages[0]
        _ = page.goto("https://www.google.com")
        screenshot = page.screenshot(path="screenshot.png")
        assert screenshot is not None
