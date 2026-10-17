import asyncio
import hashlib
import io
import json
import os
import sys

import requests
from notte_sdk import NotteClient
from playwright.async_api import async_playwright


async def _capture(cdp_url):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(cdp_url)
        try:
            page = await browser.contexts[0].new_page()
            await page.goto("https://example.com", wait_until="domcontentloaded", timeout=30_000)
            return await page.screenshot(full_page=True)
        finally:
            failed = sys.exception() is not None
            try:
                await asyncio.wait_for(browser.close(), timeout=5)
            except Exception:
                if not failed:
                    raise RuntimeError("Browser disconnect failed") from None


def capture_page():
    with NotteClient().Session(max_duration_minutes=3, proxies=False) as session:
        try:
            image = asyncio.run(_capture(session.cdp_url()))
        except Exception:
            raise RuntimeError("Could not capture the hosted page") from None
        return image, session.session_id


def upload_capture(image: bytes, session_id: str, token: str, folder_id: str, http=requests):
    step, status = "Box upload", None
    try:
        name = f"notte-{session_id}.png"
        headers = {"Authorization": f"Bearer {token}"}
        response = http.post(
            "https://upload.box.com/api/2.0/files/content",
            headers=headers,
            data={"attributes": json.dumps({"name": name, "parent": {"id": folder_id}})},
            files={"file": (name, io.BytesIO(image), "image/png")},
            timeout=60,
        )
        status = response.status_code
        response.raise_for_status()
        file_id = response.json()["entries"][0]["id"]
        step, status = "Box metadata lookup", None
        response = http.get(
            f"https://api.box.com/2.0/files/{file_id}", headers=headers, params={"fields": "id,size,sha1"}, timeout=30
        )
        status = response.status_code
        response.raise_for_status()
        stored = response.json()
        step, status = "Box content verification", None
        if stored["size"] != len(image) or stored["sha1"] != hashlib.sha1(image, usedforsecurity=False).hexdigest():
            raise RuntimeError("Box content verification failed")
        return {"box_file_id": file_id, "session_id": session_id}
    except requests.Timeout:
        raise RuntimeError(f"{step} timed out") from None
    except Exception:
        detail = f" (HTTP {status})" if status is not None and status >= 400 else ""
        raise RuntimeError(f"{step} failed{detail}") from None


def main():
    token = os.environ["BOX_ACCESS_TOKEN"]
    image, session_id = capture_page()
    return upload_capture(image, session_id, token, os.getenv("BOX_FOLDER_ID", "0"))


if __name__ == "__main__":
    print(main())
