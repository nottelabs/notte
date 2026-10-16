import asyncio
import base64
from collections.abc import Awaitable, Callable

from openai import AsyncOpenAI
from openai.types.responses import ComputerAction, ResponseComputerToolCall
from playwright.async_api import Page

KEYS = {
    "ENTER": "Enter",
    "RETURN": "Enter",
    "TAB": "Tab",
    "ESC": "Escape",
    "ESCAPE": "Escape",
    "CTRL": "Control",
    "CONTROL": "Control",
    "ALT": "Alt",
    "SHIFT": "Shift",
    "META": "Meta",
    "SPACE": "Space",
    "BACKSPACE": "Backspace",
    "DELETE": "Delete",
    "ARROWLEFT": "ArrowLeft",
    "ARROWRIGHT": "ArrowRight",
    "ARROWUP": "ArrowUp",
    "ARROWDOWN": "ArrowDown",
}


class NotteComputer:
    """Execute approved Responses computer calls on one browser viewport."""

    def __init__(self, page: Page, *, confirm: Callable[[ComputerAction], Awaitable[bool]]):
        if not page.viewport_size:
            raise ValueError("Set an explicit page viewport")
        self.page = page
        self.confirm = confirm
        self.actions: list[str] = []

    async def run(self, provider: AsyncOpenAI, task: str) -> None:
        response = await provider.responses.create(
            model="gpt-6.1-sol", tools=[{"type": "computer"}], max_output_tokens=2048, input=task
        )
        for turn in range(9):
            calls = [item for item in response.output if item.type == "computer_call"]
            if not calls:
                return
            if turn >= 8:
                raise RuntimeError("Computer turn limit exceeded")
            outputs = [await self.handle(call) for call in calls]
            response = await provider.responses.create(
                model="gpt-6.1-sol",
                tools=[{"type": "computer"}],
                max_output_tokens=2048,
                previous_response_id=response.id,
                input=outputs,
            )

    def point(self, x: float, y: float) -> None:
        viewport = self.page.viewport_size
        if not viewport or not (0 <= x < viewport["width"] and 0 <= y < viewport["height"]):
            raise ValueError("Coordinates outside the browser viewport")

    async def handle(self, call: ResponseComputerToolCall) -> dict:
        if call.pending_safety_checks:
            raise PermissionError("Computer use requires human safety review")
        if not call.actions or len(self.actions) + len(call.actions) > 64:
            raise ValueError("Missing actions or action limit exceeded")
        for action in call.actions:
            if not await self.confirm(action):
                raise PermissionError("Computer action refused")
            modifiers = [KEYS.get(key.upper(), key) for key in getattr(action, "keys", None) or []]
            if action.type == "keypress":
                await self.page.keyboard.press("+".join(modifiers))
            else:
                pressed: list[str] = []
                try:
                    for key in modifiers:
                        await self.page.keyboard.down(key)
                        pressed.append(key)
                    if action.type in ("click", "double_click", "move", "scroll"):
                        self.point(action.x, action.y)
                        await self.page.mouse.move(action.x, action.y)
                    if action.type == "click":
                        if action.button not in ("left", "right", "wheel"):
                            raise ValueError("Unsupported mouse button")
                        await self.page.mouse.click(
                            action.x, action.y, button="middle" if action.button == "wheel" else action.button
                        )
                    elif action.type == "double_click":
                        await self.page.mouse.dblclick(action.x, action.y)
                    elif action.type == "scroll":
                        await self.page.mouse.wheel(action.scroll_x, action.scroll_y)
                    elif action.type == "type":
                        if len(action.text) > 10000:
                            raise ValueError("Text exceeds the example limit")
                        await self.page.keyboard.insert_text(action.text)
                    elif action.type == "drag":
                        if not 2 <= len(action.path) <= 100:
                            raise ValueError("Drag path must contain 2 to 100 points")
                        for point in action.path:
                            self.point(point.x, point.y)
                        await self.page.mouse.move(action.path[0].x, action.path[0].y)
                        await self.page.mouse.down()
                        try:
                            for point in action.path[1:]:
                                await self.page.mouse.move(point.x, point.y)
                        finally:
                            await self.page.mouse.up()
                    elif action.type == "wait":
                        await asyncio.sleep(1)
                    elif action.type not in ("screenshot", "move"):
                        raise ValueError("Unsupported computer action")
                finally:
                    for key in reversed(pressed):
                        await self.page.keyboard.up(key)
            self.actions.append(action.type)
        image = await self.page.screenshot(type="png", scale="css")
        return {
            "type": "computer_call_output",
            "call_id": call.call_id,
            "output": {
                "type": "computer_screenshot",
                "image_url": "data:image/png;base64," + base64.b64encode(image).decode(),
                "detail": "original",
            },
        }
