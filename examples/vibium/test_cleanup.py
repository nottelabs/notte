import asyncio
import os
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import connection


class CleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_cancel_during_late_start_cleanup_retains_ownership(self):
        started, stopped, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        events = []
        remote = SimpleNamespace(stop=AsyncMock(side_effect=lambda: events.append("native-stop")))
        child = SimpleNamespace(pid=987654321, wait=AsyncMock(side_effect=lambda: events.append("driver-reap")))

        async def start(**_kwargs):
            started.set()
            await release.wait()
            return remote

        class Session:
            session_id = "owned-fixture"
            response = object()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                events.append("notte-stop")
                stopped.set()

            def cdp_url(self):
                return "ws://127.0.0.1/fixture"

        @asynccontextmanager
        async def bridge(_url):
            yield "127.0.0.1:1"

        async def enter(driver):
            driver.process = child
            return driver

        async def execute():
            async with connection.notte_vibium(SimpleNamespace(Session=lambda **_kwargs: Session())) as (
                driver,
                url,
                _id,
            ):
                await driver.connect(url)

        with (
            patch.object(connection.NativeDriver, "__aenter__", enter),
            patch.object(connection.NativeDriver, "attach", AsyncMock(return_value="ws://127.0.0.1/owned")),
            patch.object(connection, "cdp_bridge", bridge),
            patch.object(connection.browser, "start", start),
            patch.object(os, "killpg"),
        ):
            task = asyncio.create_task(execute())
            try:
                await asyncio.wait_for(started.wait(), 2)
                task.cancel()
                await asyncio.wait_for(stopped.wait(), 2)
                await asyncio.sleep(0.01)
                task.cancel()
                await asyncio.sleep(0.01)
                release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(task, 2)
                self.assertEqual(events, ["notte-stop", "native-stop", "driver-reap"])
            finally:
                release.set()
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

    async def test_cancel_during_driver_spawn_reaps_late_process(self):
        started, release = asyncio.Event(), asyncio.Event()
        child = SimpleNamespace(pid=987654321, wait=AsyncMock())

        async def spawn(*_args, **_kwargs):
            started.set()
            await release.wait()
            return child

        with (
            patch.dict(os.environ, {"CHROMEDRIVER_PATH": __file__}),
            patch.object(asyncio, "create_subprocess_exec", spawn),
            patch.object(os, "killpg") as kill,
        ):
            driver = connection.NativeDriver()
            task = asyncio.create_task(driver.__aenter__())
            await asyncio.wait_for(started.wait(), 2)
            task.cancel()
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, 2)
            kill.assert_called_once()
            self.assertEqual(kill.call_args.args[0], child.pid)
            child.wait.assert_awaited_once()

    async def test_cancelled_start_reaps_late_client_after_notte_stops(self):
        started, release = asyncio.Event(), asyncio.Event()
        events = []
        remote = SimpleNamespace(stop=AsyncMock(side_effect=lambda: events.append("native-stop")))

        async def start(**_kwargs):
            started.set()
            await release.wait()
            return remote

        class Session:
            session_id = "owned-fixture"
            response = object()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                events.append("notte-stop")
                release.set()

            def cdp_url(self):
                return "ws://127.0.0.1/fixture"

        @asynccontextmanager
        async def bridge(_url):
            yield "127.0.0.1:1"

        async def enter(driver):
            return driver

        async def execute():
            async with connection.notte_vibium(SimpleNamespace(Session=lambda **_kwargs: Session())) as (
                driver,
                url,
                _id,
            ):
                await driver.connect(url)

        with (
            patch.object(connection.NativeDriver, "__aenter__", enter),
            patch.object(connection.NativeDriver, "attach", AsyncMock(return_value="ws://127.0.0.1/owned")),
            patch.object(connection, "cdp_bridge", bridge),
            patch.object(connection.browser, "start", start),
        ):
            task = asyncio.create_task(execute())
            await asyncio.wait_for(started.wait(), 2)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, 2)
        self.assertEqual(events, ["notte-stop", "native-stop"])

    async def test_driver_delete_cannot_hide_native_cleanup_failure(self):
        driver = connection.NativeDriver()
        driver.native_id = "owned-fixture"
        driver.http = SimpleNamespace(
            delete=AsyncMock(return_value=SimpleNamespace(is_success=True)), aclose=AsyncMock()
        )
        failed = asyncio.get_running_loop().create_future()
        failed.set_exception(RuntimeError("private native failure"))
        driver.starts.append(failed)
        with self.assertRaisesRegex(RuntimeError, "^Native client cleanup failed$"):
            await driver.__aexit__(None, None, None)
        driver.http.delete.assert_awaited_once()
        driver.http.aclose.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
