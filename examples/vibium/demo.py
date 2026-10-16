import asyncio
import json
import signal
from pathlib import Path

from connection import notte_vibium


async def run_demo(url="https://example.com", selector="h1", client=None):
    async with notte_vibium(client) as (driver, bidi_url, session_id):
        async with asyncio.timeout(90):
            remote = await driver.connect(bidi_url)
            page = await remote.page()
            await page.go(url)
            text = await (await page.find(selector, timeout=1000)).text()
            title = await page.title()
            png = await page.screenshot()
            if png[:8] != b"\x89PNG\r\n\x1a\n":
                raise RuntimeError("Expected a PNG screenshot")
            await driver.disconnect(remote)
            remote = await driver.connect(bidi_url)
            if await (await remote.page()).title() != title:
                raise RuntimeError("Native reconnect changed the page")
            return {"session_id": session_id, "title": title, "text": text, "png": png}


async def cli():
    task = asyncio.current_task()
    loop = asyncio.get_running_loop()
    interrupted = False

    def cancel_once():
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            task.cancel()

    for interrupt in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(interrupt, cancel_once)
    try:
        return await run_demo()
    finally:
        for interrupt in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(interrupt)


if __name__ == "__main__":
    try:
        with asyncio.Runner() as runner:
            result = runner.run(cli())
        png = result.pop("png")
        Path("screenshot.png").write_bytes(png)
        print(json.dumps({**result, "screenshot": "screenshot.png"}))
    except (KeyboardInterrupt, asyncio.CancelledError):
        raise SystemExit(130) from None
    except Exception as error:
        raise SystemExit(str(error)) from None
