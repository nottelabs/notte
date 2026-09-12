# @sniptest filename=captcha_combine_stealth.py
# @sniptest show=1-7
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(solve_captchas=True, proxies=True, viewport_width=1920, viewport_height=1080) as session:
    # Maximum captcha success rate
    pass

status = session.status()
assert status.proxies is True
assert status.viewport_width == 1920
assert status.viewport_height == 1080
