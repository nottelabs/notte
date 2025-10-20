import json
from pathlib import Path

from notte_core.common.config import CookieDict
from notte_core.common.logging import logger


def create_or_append_cookies_to_file(cookie_file: Path, cookies: list[CookieDict]) -> None:
    logger.info(f"🍪 Automatically saving cookies to {cookie_file}")
    # Read existing cookies if file exists, else start with empty list
    if cookie_file.exists():
        with cookie_file.open("r", encoding="utf-8") as f:
            existing_cookies: list[CookieDict] = json.load(f)
    else:
        existing_cookies = []
    # Append new cookies
    existing_cookies.extend(cookies)
    with cookie_file.open("w", encoding="utf-8") as f:
        json.dump(existing_cookies, f)
