import json
from pathlib import Path

from notte_core.common.config import CookieDict
from notte_core.common.logging import logger


def _cookie_identity(cookie: CookieDict) -> tuple[object, object, object, object]:
    return (cookie.get("name"), cookie.get("domain"), cookie.get("path"), cookie.get("partitionKey"))


def create_or_append_cookies_to_file(cookie_file: Path, cookies: list[CookieDict]) -> None:
    """Merge `cookies` into the JSON list stored in `cookie_file`, one entry per cookie.

    Sessions load the file when they start, so the browser's jar on stop repeats the
    cookies it loaded: appending them blindly duplicated the whole file on every stop.
    Merging (rather than overwriting) keeps cookies another session saved to the same
    file in the meantime. A cookie is identified by name, domain, path and partition
    key; the newest value wins.
    """
    logger.info(f"🍪 Automatically saving cookies to {cookie_file}")
    existing: list[CookieDict] = []
    if cookie_file.exists():
        with cookie_file.open("r", encoding="utf-8") as f:
            existing = json.load(f)
    merged = {_cookie_identity(cookie): cookie for cookie in [*existing, *cookies]}
    with cookie_file.open("w", encoding="utf-8") as f:
        json.dump(list(merged.values()), f)
