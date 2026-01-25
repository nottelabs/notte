# @sniptest filename=realistic_delays.py
import time

from notte_sdk import NotteClient

client = NotteClient()

with client.Session(browser_type="firefox", solve_captchas=True) as session:
    page = session.page

    # Navigate to page
    page.goto("https://example.com/protected")

    # Wait for page to load
    time.sleep(2)

    # Fill form
    page.fill('input[name="email"]', "user@example.com")
    time.sleep(1)

    # Submit (captcha will be solved)
    page.click('button[type="submit"]')
