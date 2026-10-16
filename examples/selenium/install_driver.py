"""Download a matching ChromeDriver, without installing or launching Chrome."""

import asyncio
import io
import json
import platform
import time
import urllib.request
import zipfile
from pathlib import Path

import requests
from bridge import cdp_bridge
from notte_sdk import NotteClient


async def browser_major(session):
    async with cdp_bridge(session.cdp_url()) as address:
        response = await asyncio.to_thread(requests.get, f"http://{address}/json/version", timeout=10)
        response.raise_for_status()
        return response.json()["Browser"].split("/")[1].split(".")[0]


def install_driver():
    platforms = {
        ("Linux", "x86_64"): "linux64",
        ("Darwin", "arm64"): "mac-arm64",
        ("Darwin", "x86_64"): "mac-x64",
        ("Windows", "AMD64"): "win64",
    }
    target = platforms.get((platform.system(), platform.machine()))
    if not target:
        raise RuntimeError("Use a Chrome for Testing supported platform for the local driver")
    client = NotteClient()
    with client.Session(
        max_duration_minutes=1, idle_timeout_minutes=1, proxies=False, browser_type="chrome"
    ) as session:
        major = asyncio.run(browser_major(session))
    for attempt in range(30):
        status = client.sessions.status(session_id=session.session_id)
        if status.status == "closed":
            break
        time.sleep(0.5)
    if status.status != "closed":
        raise RuntimeError("The driver setup's browser did not close")
    metadata = json.load(
        urllib.request.urlopen(
            "https://googlechromelabs.github.io/chrome-for-testing/latest-versions-per-milestone-with-downloads.json",
            timeout=30,
        )
    )
    release = metadata["milestones"][major]
    url = next(x["url"] for x in release["downloads"]["chromedriver"] if x["platform"] == target)
    filename = "chromedriver.exe" if target.startswith("win") else "chromedriver"
    destination = Path(__file__).parent / ".drivers" / release["version"] / filename
    if not destination.exists():
        archive = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(url, timeout=60).read()))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(archive.read(f"chromedriver-{target}/{filename}"))
        destination.chmod(0o755)
    return destination.resolve()


if __name__ == "__main__":
    print(install_driver())
