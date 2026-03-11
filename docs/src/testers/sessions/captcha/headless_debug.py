# @sniptest filename=headless_debug.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(
    solve_captchas=True,
    headless=False,  # Opens live viewer
) as session:
    # You can watch captchas being solved
    pass
