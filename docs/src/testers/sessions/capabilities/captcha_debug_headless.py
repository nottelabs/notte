# @sniptest filename=captcha_debug_headless.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(
    browser_type="firefox",
    solve_captchas=True,
    headless=False,  # Opens live viewer
) as session:
    # You can watch captchas being solved
    pass
