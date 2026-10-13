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


def test_session_page_leaves_native_dialogs_to_backend():
    client = NotteClient()
    with client.Session(proxies=False) as session:
        page = session.page
        _ = page.goto("https://example.com")
        _ = page.evaluate("window.onbeforeunload = () => 'leave?'")

        result = session.execute(type="goto", url="https://example.org", raise_on_failure=True)

        page.wait_for_url("https://example.org/**")
        assert result.success
        assert page.title() == "Example Domain"
