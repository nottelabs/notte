# @sniptest filename=captcha_ensure_requirements.py
# @sniptest show=1-10
from notte_sdk import NotteClient

client = NotteClient()

# Ensure all requirements are met
with client.Session(
    solve_captchas=True,  # Must be enabled
    proxies=True,  # Helps with detection
) as session:
    pass

status = session.status()
assert status.proxies is True
