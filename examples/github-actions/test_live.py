import asyncio
import json
import os
import re
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
from playwright.async_api import Page
from repair import repair

SOURCE = Path(__file__).with_name("fixtures").joinpath("selectors.json").read_bytes()


def closed(sid):
    deadline = time.monotonic() + 15
    while True:
        response = requests.get(
            os.environ.get("NOTTE_API_URL", "https://api.notte.cc") + "/sessions/" + sid,
            headers={"Authorization": "Bearer " + os.environ["NOTTE_API_KEY"]},
            timeout=20,
        )
        response.raise_for_status()
        row = response.json()
        if row["status"] == "closed":
            return
        assert time.monotonic() < deadline, f"Owned browser {sid} remains active"
        time.sleep(0.5)


class LiveTests(unittest.TestCase):
    def test_idn_origins_use_browser_normalization(self):
        for hostname in ("bücher.invalid", "xn--bcher-kva.invalid", "faß.invalid", "xn--fa-hia.invalid"):
            with self.subTest(hostname=hostname):
                source = json.loads(SOURCE)
                source["url"] = "https://" + hostname + "/start"
                with asyncio.Runner() as runner:
                    result = runner.run(
                        repair(
                            json.dumps(source).encode(),
                            fixture_navigation_html='<a id="learn-more" href="/a">Learn more</a>',
                        )
                    )
                closed(result["session_id"])
                print(f"IDN {hostname}: owned browser {result['session_id']} independently closed")
                self.assertEqual(result["changes"][0]["after"], "a#learn-more")

        source["url"] = "https://faß.invalid/start"
        with asyncio.Runner() as runner, self.assertRaises(RuntimeError) as error:
            runner.run(repair(json.dumps(source).encode(), fixture_redirect="https://fass.invalid/start"))
        sid = re.search(r"session ([a-f0-9-]{36})", str(error.exception)).group(1)
        closed(sid)
        print(f"IDN foreign origin: owned browser {sid} independently closed")
        self.assertIn("origin", str(error.exception))

    def test_idn_redirect_refuses_before_frame_event(self):
        source = json.loads(SOURCE)
        source["url"] = "https://faß.invalid/start"
        original_on = Page.on

        def without_frame_event(page, event, listener):
            if event == "framenavigated":
                return page
            return original_on(page, event, listener)

        # A failed redirect can finish navigation before a later error-page frame event.
        with patch.object(Page, "on", without_frame_event), asyncio.Runner() as runner:
            with self.assertRaises(RuntimeError) as error:
                runner.run(repair(json.dumps(source).encode(), fixture_redirect="https://fass.invalid/start"))
        sid = re.search(r"session ([a-f0-9-]{36})", str(error.exception)).group(1)
        closed(sid)
        print(f"IDN before frame event: owned browser {sid} independently closed")
        self.assertIn("refused: origin", str(error.exception))

    def test_dom_backed_repair_and_refusals(self):
        cases = {
            "repair": None,
            "delayed": """<script>setTimeout(() => { document.body.innerHTML = '<a id="learn-more" href="/a">Learn more</a>'; }, 150)</script>""",
            "id": '<a id="learn-more" href="/a">Learn more</a>',
            "escaped_id": '<a id="learn:more" href="/a">Learn more</a>',
            "late_redirect": None,
            "unchanged": None,
            "missing": '<a id="other">Other</a>',
            "ambiguous": '<a href="/a">Learn more</a><a href="/b">Learn more</a>',
            "unstable": '<a role="link">Learn more</a>',
            "collision": '<a id="duplicate" href="/a">Learn more</a><a id="duplicate" href="/b">Other</a>',
            "navigation": None,
            "redirect": None,
            "cancel": None,
        }
        for mode, html in cases.items():
            with self.subTest(mode=mode):
                source = json.loads(SOURCE)
                if mode == "unchanged":
                    source["selectors"]["learn_more"]["selector"] = "a"
                if mode == "navigation":
                    source["url"] = "https://notte-selector-missing.invalid"
                if mode == "redirect":
                    source["url"] = "https://notte-selector-fixture.invalid/start"
                raw = json.dumps(source).encode()

                async def run():
                    task = asyncio.create_task(
                        repair(
                            raw,
                            fixture_html=html,
                            fixture_navigation_html=(
                                '<a href="https://www.iana.org/domains/example">Learn more</a>'
                                if mode not in {"navigation", "redirect", "cancel"}
                                else None
                            ),
                            fixture_redirect="https://example.com" if mode == "redirect" else None,
                            fixture_late_redirect="https://www.iana.org" if mode == "late_redirect" else None,
                        )
                    )
                    if mode == "cancel":
                        await asyncio.sleep(0.05)
                        task.cancel()
                    return await task

                with asyncio.Runner() as runner:
                    if mode in {"repair", "unchanged", "id", "escaped_id", "delayed"}:
                        result = runner.run(run())
                        sid = result["session_id"]
                        self.assertEqual(len(result["changes"]), 0 if mode == "unchanged" else 1)
                        if result["changes"]:
                            after = result["changes"][0]["after"]
                            if mode in {"id", "escaped_id", "delayed"}:
                                self.assertEqual(
                                    after, "a#learn-more" if mode in {"id", "delayed"} else r"a#learn\:more"
                                )
                            else:
                                self.assertTrue(after.startswith('a[href="'))
                            self.assertNotEqual(result["changes"][0]["before"], result["changes"][0]["after"])
                    else:
                        with self.assertRaises(asyncio.CancelledError if mode == "cancel" else RuntimeError) as error:
                            runner.run(run())
                        message = str(error.exception)
                        self.assertNotIn(os.environ["NOTTE_API_KEY"], message)
                        self.assertNotIn("wss:", message)
                        if mode in {"redirect", "late_redirect"}:
                            self.assertIn("origin", message)
                        sid = re.search(r"session ([a-f0-9-]{36})", message).group(1)
                closed(sid)
                print(f"{mode}: owned browser {sid} independently closed")


if __name__ == "__main__":
    unittest.main()
