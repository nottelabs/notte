# @sniptest filename=captcha_debug_headless.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(
    solve_captchas=True,
    headless=False,  # Opens live viewer
) as session:
    # You can watch captchas being solved
    pass
