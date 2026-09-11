# @sniptest filename=full_config.py
# @sniptest show=5-15
from notte_sdk import NotteClient

client = NotteClient()

with client.Session(
    advanced_stealth=False,
    solve_captchas=True,
    proxies=True,
    viewport_width=1920,
    viewport_height=1080,
    idle_timeout_minutes=10,
    browser_type="chromium",
) as session:
    page = session.page
    page.goto("https://example.com")

    # Values retained for the external test runner, outside the displayed range.
    status = session.status()
    title = page.title()
    viewport = page.evaluate("({width: window.innerWidth, height: window.innerHeight})")
