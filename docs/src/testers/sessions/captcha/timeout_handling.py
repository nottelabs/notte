# @sniptest filename=timeout_handling.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(
    browser_type="firefox",
    solve_captchas=True,
    timeout_minutes=15,  # Longer timeout
) as session:
    pass
