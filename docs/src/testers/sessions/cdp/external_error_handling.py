# @sniptest filename=external_error_handling.py
from notte_sdk import NotteClient

client = NotteClient()

cdp_url = "wss://provider.com:9222/devtools/browser/abc123"

try:
    with client.Session(cdp_url=cdp_url) as session:
        # Your automation
        pass
except Exception as e:
    print(f"Automation failed: {e}")
    # Implement retry logic or fallback
