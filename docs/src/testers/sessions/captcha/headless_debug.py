# @sniptest filename=headless_debug.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(
    solve_captchas=True,
    open_viewer=True,
) as session:
    # You can watch captchas being solved
    pass
