"""Real native SDK acceptance against one isolated local browser, without Notte."""

import asyncio
import os
import shutil
import signal
import subprocess
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

from bridge import cdp_bridge
from connection import NativeDriver

HTML = """<title>Owned native fixture</title><input id="value"><button id="copy"
onclick="document.querySelector('output').textContent=document.querySelector('input').value">Copy</button><output></output>"""


@unittest.skipUnless(os.getenv("VIBIUM_TEST_CHROME"), "requires an explicitly selected isolated test Chrome")
class NativeTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_python_and_typescript_clients(self):
        with tempfile.TemporaryDirectory(prefix="notte-vibium-") as profile:
            clean = {k: os.environ[k] for k in ("PATH", "HOME", "TMPDIR") if k in os.environ}
            process = await asyncio.create_subprocess_exec(
                os.environ["VIBIUM_TEST_CHROME"],
                "--headless=new",
                "--no-sandbox",
                "--no-first-run",
                "--disable-background-networking",
                "--disable-sync",
                "--remote-debugging-port=0",
                f"--user-data-dir={profile}",
                "about:blank",
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=clean,
                start_new_session=True,
            )
            try:
                active = Path(profile) / "DevToolsActivePort"
                async with asyncio.timeout(15):
                    while not active.exists() or len(active.read_text().splitlines()) < 2:
                        self.assertIsNone(process.returncode, "Owned native browser exited before readiness")
                        await asyncio.sleep(0.05)
                port, path = active.read_text().splitlines()[:2]
                cdp = f"ws://127.0.0.1:{port}{path}"
                async with asyncio.timeout(90):
                    await self.python_case(cdp)
                    child = await asyncio.create_subprocess_exec(
                        shutil.which("node"),
                        "test/native.ts",
                        cwd=Path(__file__).parent,
                        env={**clean, "VIBIUM_TEST_CDP": cdp, "CHROMEDRIVER_PATH": os.environ["CHROMEDRIVER_PATH"]},
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    try:
                        await asyncio.wait_for(child.communicate(), 60)
                        self.assertEqual(
                            child.returncode, 0, "TypeScript native acceptance failed; raw details withheld"
                        )
                    finally:
                        if child.returncode is None:
                            child.kill()
                            await child.wait()
            finally:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(process.wait(), 3)
                except TimeoutError:
                    os.killpg(process.pid, signal.SIGKILL)
                    await process.wait()

    async def python_case(self, cdp):
        async with cdp_bridge(cdp) as address:
            async with NativeDriver() as driver:
                bidi = await driver.attach(address)
                remote = await driver.connect(bidi)
                page = await remote.page()
                await page.go("data:text/html," + quote(HTML))
                await (await page.find("#value")).fill("native-python")
                await (await page.find("#copy")).click()
                self.assertEqual(await (await page.find("output")).text(), "native-python")
                png = await page.screenshot()
                self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
                self.assertGreater(len(png), 100)
                await driver.disconnect(remote)
                remote = await driver.connect(bidi)
                self.assertEqual(await (await remote.page()).title(), "Owned native fixture")
                with self.assertRaises(Exception):
                    await (await remote.page()).find("#absent-owned-fixture", timeout=250)
                task = asyncio.create_task((await remote.page()).find("#cancelled-owned-fixture", timeout=30_000))
                await asyncio.sleep(0.1)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task


if __name__ == "__main__":
    unittest.main()
