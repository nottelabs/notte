# @sniptest filename=combine_stealth.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(
    browser_type="firefox", solve_captchas=True, proxies=True, viewport_width=1920, viewport_height=1080
) as session:
    # Maximum captcha success rate
    pass
