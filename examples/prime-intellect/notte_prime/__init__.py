"""A browser-backed Verifiers taskset with one owned session per rollout."""

import asyncio

import verifiers.v1 as vf
from notte_sdk import NotteClient
from playwright.async_api import async_playwright
from verifiers.v1.harnesses.null.harness import NullHarness

__all__ = ["NotteTaskset", "NotteEnv", "NullHarness"]


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
                    await browser.close()
        except Exception:
            raise RuntimeError("The browser task failed") from None


class BrowserData(vf.TaskData):
    expected_title: str = "Example Domain"
    url: str = "https://example.com"


class BrowserTask(vf.Task[BrowserData, BrowserState, vf.TaskConfig]):
    async def setup(self, trace, runtime):
        await self.close()
        self.session = NotteClient().Session(max_duration_minutes=3)
        try:
            await asyncio.to_thread(self.session.start)
            trace.state.session_id = self.session.session_id
            trace.state.cdp_url = self.session.cdp_url()
        except Exception:
            await self.close()
            raise RuntimeError("Could not prepare the rollout browser") from None

    async def finalize(self, trace, runtime):
        try:
            await self.close()
        finally:
            trace.state.cdp_url = ""

    async def close(self):
        if getattr(self, "session", None):
            if self.session.session_id:
                await asyncio.to_thread(self.session.stop)
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
            await task.close()
