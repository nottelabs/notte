# @sniptest filename=ensure_requirements.py
from notte_sdk import NotteClient

client = NotteClient()

# Ensure all requirements are met
with client.Session(
    browser_type="firefox",  # Must be Firefox
    solve_captchas=True,  # Must be enabled
    proxies=True,  # Helps with detection
) as session:
    pass
