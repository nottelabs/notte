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


async def repair(
    source: bytes,
    *,
    fixture_html: str | None = None,
    fixture_navigation_html: str | None = None,
    fixture_redirect: str | None = None,
    fixture_late_redirect: str | None = None,
) -> dict:
    document = read_map(source)
    browser = NotteClient().Session(max_duration_minutes=3)
    stage = "claim"
    try:
        async with browser:
            try:
                async with asyncio.timeout(90):
                    page = await (await browser.apage).context.new_page()
                    if page.url != "about:blank":
                        raise ValueError("Expected a fresh blank page")
                    navigation_url = await page.evaluate("url => new URL(url).href", document["url"])

                    def origin(url):
                        parsed = urlsplit(url)
                        return parsed.scheme, parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)

                    expected = origin(navigation_url)
                    changed_origin = False

                    def requested(request):
                        nonlocal changed_origin, stage
                        # Routing only intercepts the first URL of an HTTP redirect.
                        if (
                            request.is_navigation_request()
                            and request.frame == page.main_frame
                            and origin(request.url) != expected
                        ):
                            changed_origin = True
                            stage = "origin"

                    async def guard_navigation(route):
                        nonlocal changed_origin, stage
                        request = route.request
                        if (
                            request.is_navigation_request()
                            and request.frame == page.main_frame
                            and origin(request.url) != expected
                        ):
                            changed_origin = True
                            stage = "origin"
                            await route.abort()
                        else:
                            await route.continue_()

                    def navigated(frame):
                        nonlocal changed_origin, stage
                        if frame == page.main_frame and origin(frame.url) != expected:
                            changed_origin = True
                            stage = "origin"

                    page.on("request", requested)
                    page.on("framenavigated", navigated)
                    await page.route("**/*", guard_navigation)
                    if fixture_redirect is not None:
                        await page.route(
                            navigation_url,
                            lambda route: route.fulfill(status=302, headers={"location": fixture_redirect}, body=""),
                        )
                    if fixture_navigation_html is not None:
                        await page.route(
                            navigation_url,
                            lambda route: route.fulfill(content_type="text/html", body=fixture_navigation_html),
                        )
                    stage = "navigation"
                    await page.goto(document["url"], wait_until="domcontentloaded", timeout=30_000)
                    stage = "origin"

                    def check_origin():
                        if changed_origin or origin(page.url) != expected:
                            raise ValueError("Navigation changed origin")

                    check_origin()
                    stage = "DOM"
                    if fixture_html is not None:
                        await page.set_content(fixture_html)
                    if fixture_late_redirect is not None:
                        async with page.expect_event("requestfailed"):
                            await page.evaluate("url => { location.href = url; }", fixture_late_redirect)
                    stage = "origin"
                    check_origin()
                    stage = "DOM"
                    changes = []
                    for key, entry in document["selectors"].items():
                        target = page.get_by_role(entry["role"], name=entry["name"], exact=True)
                        await target.first.wait_for(state="attached", timeout=5_000)
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
                    stage = "origin"
                    check_origin()
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
    interrupted = {"code": 0}

    async def main():
        task = asyncio.current_task()
        loop = asyncio.get_running_loop()

        def interrupt(exit_code):
            if not interrupted["code"]:
                interrupted["code"] = exit_code
                task.cancel()

        previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
        try:
            loop.add_signal_handler(signal.SIGINT, interrupt, 130)
            loop.add_signal_handler(signal.SIGTERM, interrupt, 143)
            return await repair((directory / "selectors.json").read_bytes())
        finally:
            for sig, handler in previous.items():
                loop.remove_signal_handler(sig)
                signal.signal(sig, handler)

    try:
        with asyncio.Runner() as runner:
            result = runner.run(main())
    except (asyncio.CancelledError, KeyboardInterrupt) as error:
        print(str(error) or "Selector repair interrupted")
        raise SystemExit(interrupted["code"] or 130) from None
    (directory / "proposal.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"session_id": result["session_id"], "changed": len(result["changes"])}))
