"""A browser-backed Verifiers taskset with one owned session per rollout."""

import asyncio
import sys

import verifiers.v1 as vf
from notte_sdk import NotteClient
from playwright.async_api import async_playwright
from verifiers.v1.harnesses.null.harness import NullHarness

__all__ = ["NotteTaskset", "NotteEnv", "NullHarness"]


class _BrowserCleanupError(RuntimeError):
    pass


class BrowserState(vf.State):
    session_id: str = ""
    cdp_url: str = ""
    title: str = ""
    url: str = ""


class BrowserTools(vf.Toolset[vf.ToolsetConfig, BrowserState]):
    TOOL_PREFIX = None

    @vf.tool
    async def read_page(self, url: str) -> str:
        """Open a page in this rollout's browser and return its title."""
        if not self.state.cdp_url:
            raise RuntimeError("The rollout browser is unavailable")
        try:
            async with async_playwright() as driver:
                browser = await driver.chromium.connect_over_cdp(self.state.cdp_url)
                try:
                    page = await browser.contexts[0].new_page()
                    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    self.state.title = await page.title()
                    self.state.url = page.url
                    return self.state.title
                finally:
                    failed = sys.exception() is not None
                    try:
                        await asyncio.wait_for(browser.close(), timeout=5)
                    except Exception:
                        if not failed:
                            raise RuntimeError("Browser disconnect failed") from None
        except Exception:
            raise RuntimeError("The browser task failed") from None


class BrowserData(vf.TaskData):
    expected_title: str = "Example Domain"
    url: str = "https://example.com"


class BrowserTask(vf.Task[BrowserData, BrowserState, vf.TaskConfig]):
    async def setup(self, trace, runtime):
        await self.close()
        self.session = NotteClient().Session(max_duration_minutes=3)
        starting = asyncio.create_task(asyncio.to_thread(self.session.start))
        try:
            await asyncio.shield(starting)
            trace.state.session_id = self.session.session_id
            trace.state.cdp_url = self.session.cdp_url()
        except BaseException as error:
            # Finish owned I/O before propagating even repeated cancellation.
            async def finish(operation):
                nonlocal error
                while True:
                    try:
                        return await asyncio.shield(operation)
                    except asyncio.CancelledError as cancelled:
                        if operation.cancelled():
                            raise
                        error = cancelled

            try:
                await finish(starting)
            except (Exception, asyncio.CancelledError):
                pass
            cleanup_failure = None
            try:
                await finish(asyncio.create_task(self.close()))
            except _BrowserCleanupError as cleanup:
                cleanup_failure = cleanup
            primary = (
                error if not isinstance(error, Exception) else RuntimeError("Could not prepare the rollout browser")
            )
            if cleanup_failure is not None:
                primary.add_note(str(cleanup_failure))
            raise primary from None

    async def finalize(self, trace, runtime):
        try:
            await self.close()
        finally:
            trace.state.cdp_url = ""

    async def close(self):
        if getattr(self, "session", None):
            if self.session.response is not None:
                try:
                    await asyncio.to_thread(self.session.stop)
                except Exception:
                    raise _BrowserCleanupError(
                        f"Could not close the rollout browser (session {self.session.session_id})"
                    ) from None
            self.session = None

    @classmethod
    def toolsets(cls, config):
        return [BrowserTools(vf.ToolsetConfig())]

    @vf.reward
    async def title_matches(self, trace) -> float:
        return float(
            trace.state.title == self.data.expected_title and trace.state.url.rstrip("/") == self.data.url.rstrip("/")
        )


class NotteTaskset(vf.Taskset[BrowserTask, vf.TasksetConfig]):
    def load(self):
        yield BrowserTask(
            BrowserData(prompt="Use read_page to visit https://example.com and report its title."),
            self.config.task,
        )


class NotteEnv(vf.SingleAgentEnv):
    async def run(self, task, agents):
        try:
            await agents.agent.run(task)
        finally:
            # Verifiers skips task finalization after setup or provider errors.
            primary = sys.exception()
            try:
                await task.close()
            except Exception as cleanup:
                if primary is None:
                    raise
                primary.add_note(
                    str(cleanup) if isinstance(cleanup, _BrowserCleanupError) else "Rollout browser cleanup failed"
                )
