# @sniptest filename=combine_stealth.py
# @sniptest show=1-12
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(
    proxies=True,
    viewport_width=1920,
    viewport_height=1080,
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
) as session:
    # Maximum stealth configuration
    pass

status = session.status()
assert status.proxies is True
assert status.viewport_width == 1920
assert status.viewport_height == 1080
assert status.user_agent == "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
