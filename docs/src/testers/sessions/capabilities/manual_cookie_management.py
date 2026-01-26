# @sniptest filename=manual_cookie_management.py
import json

from notte_sdk import NotteClient

client = NotteClient()

# Save cookies from a session
with client.Session() as session:
    page = session.page
    page.goto("https://example.com")

    # Perform login...

    # Get and save cookies
    cookies = session.get_cookies()
    with open("cookies.json", "w") as f:
        json.dump(cookies, f)

# Load cookies in a new session
with client.Session() as session:
    with open("cookies.json", "r") as f:
        cookies = json.load(f)
    session.set_cookies(cookies=cookies)

    page = session.page
    page.goto("https://example.com/dashboard")
    # Already authenticated
