# @sniptest filename=external_cleanup.py
from notte_sdk import NotteClient

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
