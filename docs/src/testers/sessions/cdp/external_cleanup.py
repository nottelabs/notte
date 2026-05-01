# @sniptest filename=external_cleanup.py
# @sniptest show=14-26
from notte_sdk import NotteClient


class ExternalBrowser:
    cdp_url: str = "ws://localhost:9222"
    id: str = "browser_123"


class Provider:
    def create(self) -> ExternalBrowser:
        return ExternalBrowser()

    def delete(self, browser_id: str) -> None:
        pass


provider = Provider()
client = NotteClient()

try:
    # Create external browser
    external_browser = provider.create()

    # Use with Notte
    with client.Session(cdp_url=external_browser.cdp_url) as session:
        # Your automation
        pass

finally:
    # Always clean up
    provider.delete(external_browser.id)
