# @sniptest filename=browser_type_selection.py
from typing import Literal

from notte_sdk import NotteClient

client = NotteClient()

# Try different browser types
BrowserType = Literal["chromium", "chrome", "firefox"]
browsers: list[BrowserType] = ["chromium", "chrome", "firefox"]
for browser in browsers:
    with client.Session(browser_type=browser, proxies=True, solve_captchas=True) as session:
        result = session.observe(url="https://example.com")
        print(f"Success with {browser}")
