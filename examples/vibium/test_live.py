import asyncio
import os
import threading
import unittest
from unittest.mock import patch
from urllib.parse import quote

from connection import notte_vibium
from notte_sdk import NotteClient

HTML = """<title>Owned Vibium task</title><input id="value"><button id="copy"
onclick="document.querySelector('output').textContent=document.querySelector('input').value">Copy</button><output></output>"""
URL = "data:text/html," + quote(HTML)


@unittest.skipUnless(os.getenv("NOTTE_VIBIUM_LIVE") == "1", "requires an explicitly selected Notte environment")
class LiveTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = NotteClient()
        self.session_id = None
        self.actions_completed = False

    async def asyncTearDown(self):
        if self.session_id:
            for _ in range(40):
                status = await asyncio.to_thread(self.client.sessions.status, session_id=self.session_id)
                if status.status == "closed":
                    return
                await asyncio.sleep(0.25)
            self.fail("Independent API status did not confirm the owned session closed")

    async def task(self, *, fail=False, waiting=None):
        async with notte_vibium(self.client) as (driver, url, session_id):
            self.session_id = session_id
            async with asyncio.timeout(90):
                remote = await driver.connect(url)
                page = await remote.page()
                await page.go(URL)
                await (await page.find("#value")).fill("native-action")
                await (await page.find("#copy")).click()
                self.assertEqual(await (await page.find("output")).text(), "native-action")
                self.actions_completed = True
                if waiting is not None:
                    waiting.set()
                    await page.find("#absent-owned-fixture", timeout=30_000)
                if fail:
                    await page.find("#absent-owned-fixture", timeout=250)
                png = await page.screenshot()
                self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
                self.assertGreater(len(png), 100)
                await driver.disconnect(remote)
                remote = await driver.connect(url)
                self.assertEqual(await (await remote.page()).title(), "Owned Vibium task")
                await driver.disconnect(remote)

    async def test_native_actions_png_and_reconnect(self):
        await self.task()

    async def test_genuine_native_error_closes_owned_session(self):
        with self.assertRaisesRegex(RuntimeError, r"Vibium failed \(session [a-f0-9-]+\)"):
            await self.task(fail=True)
        self.assertTrue(self.actions_completed, "The failure must follow actual native browser actions")

    async def test_native_command_cancellation_closes_owned_session(self):
        waiting = asyncio.Event()
        task = asyncio.create_task(self.task(waiting=waiting))
        try:
            await asyncio.wait_for(waiting.wait(), 90)
            await asyncio.sleep(0.1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, 150)
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def test_claim_cancellation_reaps_late_owned_session(self):
        claimed, release = threading.Event(), threading.Event()
        original = self.client.sessions.start

        def start(**kwargs):
            response = original(**kwargs)
            self.session_id = response.session_id
            claimed.set()
            if not release.wait(15):
                raise TimeoutError("Owned claim fixture was not released")
            return response

        with patch.object(self.client.sessions, "start", start):
            task = asyncio.create_task(self.task())
            try:
                async with asyncio.timeout(70):
                    while not claimed.is_set() and not task.done():
                        await asyncio.sleep(0.05)
                self.assertTrue(claimed.is_set(), "A real owned session must be allocated")
                task.cancel()
                release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(task, 30)
                self.assertFalse(self.actions_completed)
            finally:
                release.set()
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)


if __name__ == "__main__":
    unittest.main()
