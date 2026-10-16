import hashlib
import io
import json
import os

import requests
from notte_sdk import NotteClient
from playwright.sync_api import sync_playwright


def capture_page():
    with NotteClient().Session(max_duration_minutes=3, proxies=False) as session:
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.connect_over_cdp(session.cdp_url())
                try:
                    page = browser.contexts[0].new_page()
                    page.goto("https://example.com", wait_until="domcontentloaded", timeout=30_000)
                    image = page.screenshot(full_page=True)
                finally:
                    browser.close()
        except Exception:
            raise RuntimeError("Could not capture the hosted page") from None
        return image, session.session_id


def upload_capture(image: bytes, session_id: str, token: str, folder_id: str, http=requests):
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
        response.raise_for_status()
        file_id = response.json()["entries"][0]["id"]
        response = http.get(
            f"https://api.box.com/2.0/files/{file_id}", headers=headers, params={"fields": "id,size,sha1"}, timeout=30
        )
        response.raise_for_status()
        stored = response.json()
        if stored["size"] != len(image) or stored["sha1"] != hashlib.sha1(image, usedforsecurity=False).hexdigest():
            raise RuntimeError("Box content verification failed")
        return {"box_file_id": file_id, "session_id": session_id}
    except Exception:
        raise RuntimeError("Could not upload and verify the Box capture") from None


def main():
    token = os.environ["BOX_ACCESS_TOKEN"]
    image, session_id = capture_page()
    return upload_capture(image, session_id, token, os.getenv("BOX_FOLDER_ID", "0"))


if __name__ == "__main__":
    print(main())
