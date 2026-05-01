# @sniptest filename=external_cdp_auth.py
from notte_sdk import NotteClient

client = NotteClient()

# CDP URL with authentication
cdp_url = "wss://user:password@provider.com:9222/devtools/browser/abc123"

with client.Session(cdp_url=cdp_url) as session:
    # Your automation
    pass
