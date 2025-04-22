from notte_sdk.client import NotteClient
from patchright.sync_api import sync_playwright


def test_cdp_connection():
    client = NotteClient()

    # start notte session
    session = client.sessions.start()

    debug_info = client.sessions.debug_info(session.session_id)

    # connect using CDP
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(debug_info.ws_url)
        page = browser.contexts[0].pages[0]
        _ = page.goto("https://www.google.com")
        screenshot = page.screenshot(path="screenshot.png")
        assert screenshot is not None

    _ = client.sessions.close(session.session_id)
