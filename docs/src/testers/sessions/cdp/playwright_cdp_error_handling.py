# @sniptest filename=playwright_cdp_error_handling.py
# @sniptest show=1-30
import time

from notte_sdk import NotteClient
from playwright.sync_api import Browser, Playwright, sync_playwright  # type: ignore[import-not-found]

# Network failures before the WebSocket upgrade. An HTTP answer (403, 410, 503) is not one of them.
TRANSPORT_ERRORS = (
    "socket hang up",
    "ECONNRESET",
    "ECONNREFUSED",
    "ETIMEDOUT",
    "Client network socket disconnected before secure TLS connection was established",
)


def connect(p: Playwright, cdp_url: str) -> Browser:
    """Connect over CDP, once more if the connection dropped before the server answered."""
    try:
        return p.chromium.connect_over_cdp(cdp_url)
    except Exception as e:
        if not any(error in str(e).partition("\n")[0] for error in TRANSPORT_ERRORS):
            raise
    time.sleep(0.3)
    return p.chromium.connect_over_cdp(cdp_url)


client = NotteClient()

with client.Session() as session:
    cdp_url = session.cdp_url()
    with sync_playwright() as p:
        try:
            browser = connect(p, cdp_url)
            # ... operations
        except Exception as e:
            print(f"CDP connection failed: {e}")
        else:
            # Capture successful connection outside the displayed error-handling example.
            if not browser.is_connected():
                raise RuntimeError("CDP browser is not connected")
            status = session.status()
