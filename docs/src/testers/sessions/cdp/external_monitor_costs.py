# @sniptest filename=external_monitor_costs.py
import time

from notte_sdk import NotteClient

client = NotteClient()

cdp_url = "wss://provider.com:9222/devtools/browser/abc123"

start = time.time()

with client.Session(cdp_url=cdp_url) as session:
    # Your automation
    pass

duration = time.time() - start
print(f"Session duration: {duration:.2f} seconds")
