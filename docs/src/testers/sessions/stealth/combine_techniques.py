# @sniptest filename=combine_techniques.py
# @sniptest show=1-11
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(
    proxies=True,
    viewport_width=1920,
    viewport_height=1080,
) as session:
    # Maximum stealth configuration
    pass

status = session.status()
assert status.proxies is True
assert status.viewport_width == 1920
assert status.viewport_height == 1080
