import tempfile

from notte_sdk.client import NotteClient
from patchright.sync_api import sync_playwright


def test_cdp_connection():
    client = NotteClient()
    with client.Session(proxies=False) as session:
        # get cdp url
        cdp_url = session.cdp_url()
        # connect using CDP
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(cdp_url)
            page = browser.contexts[0].pages[0]
            _ = page.goto("https://www.google.com")
            with tempfile.TemporaryDirectory() as tmp_dir:
                screenshot = page.screenshot(path=f"{tmp_dir}/screenshot.png")
            assert screenshot is not None
