import asyncio
import hashlib
import json
import signal
from pathlib import Path
from urllib.parse import urlsplit

from notte_sdk import NotteClient
from proposal import read_map

# Fixed DOM inspection code. Proposed selectors are always data, never executable code.
CANDIDATE = """el => {
  if (el.id && el.id.length <= 128) return `${el.localName}#${CSS.escape(el.id)}`;
  const href = el.getAttribute('href');
  if (!href || href.length > 500) return null;
  const url = new URL(href, document.baseURI);
  if (!['http:', 'https:'].includes(url.protocol) || url.search || url.hash || url.username || url.password) return null;
  return `${el.localName}[href="${CSS.escape(href)}"]`;
}"""


async def repair(source: bytes, *, fixture_html: str | None = None, fixture_redirect: str | None = None) -> dict:
    document = read_map(source)
    browser = NotteClient().Session(max_duration_minutes=3)
    stage = "claim"
    try:
        async with browser:
            try:
                async with asyncio.timeout(90):
                    page = await browser.apage
                    if fixture_redirect is not None:
                        await page.route(
                            document["url"],
                            lambda route: route.fulfill(status=302, headers={"location": fixture_redirect}, body=""),
                        )
                    stage = "navigation"
                    await page.goto(document["url"], wait_until="domcontentloaded", timeout=30_000)
                    stage = "origin"
                    expected, actual = urlsplit(document["url"]), urlsplit(page.url)

                    def origin(url):
                        return url.scheme, url.hostname, url.port or (443 if url.scheme == "https" else 80)

                    if origin(expected) != origin(actual):
                        raise ValueError("Navigation changed origin")
                    stage = "DOM"
                    if fixture_html is not None:
                        await page.set_content(fixture_html)
                    changes = []
                    for key, entry in document["selectors"].items():
                        target = page.get_by_role(entry["role"], name=entry["name"], exact=True)
                        if await target.count() != 1:
                            raise ValueError("Expected exactly one semantic target")
                        before = entry["selector"]
                        try:
                            valid = await page.locator("css=" + before).count() == 1 and await target.evaluate(
                                "(el, selector) => el.matches(selector)", before
                            )
                        except Exception:
                            valid = False
                        if valid:
                            continue
                        after = await target.evaluate(CANDIDATE)
                        if not after or await page.locator("css=" + after).count() != 1:
                            raise ValueError("No unique stable replacement")
                        if not await target.evaluate("(el, selector) => el.matches(selector)", after):
                            raise ValueError("Replacement does not identify the expected target")
                        changes.append({"key": key, "before": before, "after": after})
                    return {
                        "version": 1,
                        "source_sha256": hashlib.sha256(source).hexdigest(),
                        "session_id": browser.session_id,
                        "changes": changes,
                    }
            except asyncio.CancelledError:
                raise asyncio.CancelledError(f"Selector repair cancelled (session {browser.session_id})") from None
            except Exception:
                # The SDK logs context errors; discard page/CDP details before cleanup.
                raise RuntimeError(f"Selector repair refused: {stage} (session {browser.session_id})") from None
    except asyncio.CancelledError:
        sid = browser.session_id if browser.response is not None else "unallocated"
        raise asyncio.CancelledError(f"Selector repair cancelled (session {sid})") from None
    except Exception:
        sid = browser.session_id if browser.response is not None else "unallocated"
        raise RuntimeError(f"Selector repair refused: {stage} (session {sid})") from None


if __name__ == "__main__":
    directory = Path(__file__).parent
    interrupted = {"code": 130}

    async def main():
        task = asyncio.current_task()
        loop = asyncio.get_running_loop()

        def terminate():
            interrupted["code"] = 143
            task.cancel()

        loop.add_signal_handler(signal.SIGTERM, terminate)
        try:
            return await repair((directory / "selectors.json").read_bytes())
        finally:
            loop.remove_signal_handler(signal.SIGTERM)

    try:
        with asyncio.Runner() as runner:
            result = runner.run(main())
    except (asyncio.CancelledError, KeyboardInterrupt) as error:
        print(str(error) or "Selector repair interrupted")
        raise SystemExit(interrupted["code"]) from None
    (directory / "proposal.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"session_id": result["session_id"], "changed": len(result["changes"])}))
