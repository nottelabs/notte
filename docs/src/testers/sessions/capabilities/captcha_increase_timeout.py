# @sniptest filename=captcha_increase_timeout.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(
    browser_type="firefox",
    solve_captchas=True,
    idle_timeout_minutes=15,  # Longer timeout
) as session:
    pass
