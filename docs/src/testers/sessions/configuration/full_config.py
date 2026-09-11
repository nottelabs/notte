# @sniptest filename=full_config.py
import json

from notte_sdk import NotteClient

client = NotteClient()

with client.Session(
    idle_timeout_minutes=10,
    advanced_stealth=False,
    solve_captchas=True,
    proxies=True,
    viewport_width=1920,
    viewport_height=1080,
    browser_type="chromium",
) as session:
    status = session.status()
    if status.status != "active":
        raise RuntimeError("Session is not active")
    page = session.page
    page.goto("https://example.com")
    print(
        json.dumps(
            {
                "session_id": session.session_id,
                "status": status.status,
                "idle_timeout_minutes": status.idle_timeout_minutes,
                "title": page.title(),
                "viewport": page.evaluate("({width: window.innerWidth, height: window.innerHeight})"),
            }
        )
    )
# Automatically stopped here.
