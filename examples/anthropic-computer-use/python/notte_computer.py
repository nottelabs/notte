import asyncio
import base64

from anthropic.tools import (
    BetaAsyncAbstractComputerToolset20260801,
    BetaScreenshotResult,
    BetaToolsetCallContext,
    ToolError,
)
from anthropic.tools.computer import BetaAsyncComputerConfirmCallable
from anthropic.types.beta import (
    BetaComputerKeyInput,
    BetaComputerLeftClickInput,
    BetaComputerScreenshotInput,
    BetaComputerTypeInput,
    BetaComputerWaitInput,
)
from playwright.async_api import Page


class NotteComputer(BetaAsyncAbstractComputerToolset20260801):
    """Expose a Notte page's viewport through Anthropic's computer toolset."""

    def __init__(self, page: Page, *, confirm: BetaAsyncComputerConfirmCallable):
        if not page.viewport_size:
            raise ValueError("Set the Playwright viewport before creating the computer toolset")
        super().__init__(confirm=confirm)
        self.page = page
        self.cursor = (0, 0)

    async def screenshot(
        self, context: BetaToolsetCallContext, input: BetaComputerScreenshotInput
    ) -> BetaScreenshotResult:
        image = await self.page.screenshot(type="png", scale="css")
        return BetaScreenshotResult(data=base64.b64encode(image).decode(), media_type="image/png")

    async def left_click(self, context: BetaToolsetCallContext, input: BetaComputerLeftClickInput) -> None:
        if input.text:
            raise ToolError("Modifier clicks are not supported")
        x, y = input.coordinate or self.cursor
        viewport = self.page.viewport_size
        if not viewport or not (0 <= x < viewport["width"] and 0 <= y < viewport["height"]):
            raise ToolError("Click coordinates are outside the page viewport")
        await self.page.mouse.click(x, y)
        self.cursor = (x, y)

    async def type(self, context: BetaToolsetCallContext, input: BetaComputerTypeInput) -> None:
        await self.page.keyboard.insert_text(input.text)

    async def key(self, context: BetaToolsetCallContext, input: BetaComputerKeyInput) -> None:
        aliases = {"Return": "Enter", "ctrl": "Control", "alt": "Alt", "shift": "Shift", "super": "Meta"}
        keys = "+".join(aliases.get(part, part) for part in input.text.split("+"))
        repeat = input.repeat or 1
        if not 1 <= repeat <= 100:
            raise ToolError("Key repeat must be between 1 and 100")
        for _ in range(repeat):
            await self.page.keyboard.press(keys)

    async def wait(self, context: BetaToolsetCallContext, input: BetaComputerWaitInput) -> None:
        if not 0 <= input.duration <= 300:
            raise ToolError("Wait duration must be between 0 and 300 seconds")
        await asyncio.sleep(input.duration)
