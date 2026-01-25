# @sniptest filename=monitor_failures.py
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(browser_type="firefox", solve_captchas=True) as session:
    page = session.page
    page.goto("https://example.com/protected")

    try:
        page.click('button[type="submit"]')
        page.wait_for_url("**/success", timeout=30000)  # 30 seconds
    except Exception as e:
        print(f"Captcha solving may have failed: {e}")
        # Handle failure
