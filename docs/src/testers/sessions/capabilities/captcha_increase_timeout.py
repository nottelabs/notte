# @sniptest filename=captcha_increase_timeout.py
# @sniptest show=1-9
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(
    solve_captchas=True,
    idle_timeout_minutes=15,  # Longer timeout
) as session:
    pass

status = session.status()
assert status.idle_timeout_minutes == 15
