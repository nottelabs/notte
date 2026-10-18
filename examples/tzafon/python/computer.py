import asyncio
import base64
from collections.abc import Awaitable, Callable

from playwright.async_api import Page
from tzafon import AsyncLightcone

MODEL = "tzafon.northstar-cua-fast-1.6"


def pixel(value: float, dimension: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 999:
        raise ValueError("Expected a model coordinate from 0 to 999")
    return int(value * dimension / 1000)


class NotteComputer:
    """A bounded Lightcone loop for an approved browser form."""

    def __init__(self, page: Page, approve: Callable[[dict], Awaitable[bool]]):
        if not page.viewport_size:
            raise ValueError("Set a browser viewport")
        self.page = page
        self.approve = approve
        self.actions: list[str] = []

    async def screenshot(self) -> str:
        image = await self.page.screenshot(type="png", scale="css")
        return "data:image/png;base64," + base64.b64encode(image).decode()

    async def handle(self, call: dict) -> dict:
        if call.get("pending_safety_checks"):
            raise PermissionError("Safety review is required")
        action = call["action"]
        if not await self.approve(action):
            raise PermissionError("Computer action refused")
        kind = action["type"]
        if kind in ["type", "point_and_type"]:
            text = action["text"]
            if not isinstance(text, str) or len(text) > 1000:
                raise ValueError("Text exceeds the form limit")
        if kind in ["click", "point_and_type"]:
            viewport = self.page.viewport_size
            if not viewport:
                raise ValueError("Missing browser viewport")
            x, y = pixel(action["x"], viewport["width"]), pixel(action["y"], viewport["height"])
            if kind == "click" and action.get("button", "left") != "left":
                raise ValueError("This form example only permits left clicks")
            await self.page.mouse.click(x, y)
        if kind in ["type", "point_and_type"]:
            await self.page.keyboard.insert_text(text)
        elif kind == "keypress":
            keys = action["keys"]
            if not keys or not all(key.upper() in ["ENTER", "RETURN", "TAB"] for key in keys):
                raise PermissionError("This form example only permits Enter and Tab")
            for key in keys:
                await self.page.keyboard.press("Enter" if key.upper() in ["ENTER", "RETURN"] else "Tab")
        elif kind == "wait":
            await asyncio.sleep(0.25)
        elif kind not in ["screenshot", "click"]:
            raise ValueError("Unsupported form action")
        self.actions.append(kind)
        return {
            "type": "computer_call_output",
            "call_id": call["call_id"],
            "output": {"type": "computer_screenshot", "image_url": await self.screenshot()},
        }

    async def run(self, provider: AsyncLightcone, task: str) -> None:
        viewport = self.page.viewport_size
        assert viewport
        history = [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": task},
                    {"type": "input_image", "image_url": await self.screenshot(), "detail": "auto"},
                ],
            }
        ]
        for turn in range(9):
            response = await provider.responses.create(
                model=MODEL,
                tools=[
                    {
                        "type": "computer_use",
                        "environment": "browser",
                        "display_width": viewport["width"],
                        "display_height": viewport["height"],
                    }
                ],
                input=history,
                store=False,
                max_output_tokens=2048,
            )
            if response.status != "completed":
                raise RuntimeError("Model response did not complete")
            output = [item.model_dump(exclude_none=True) for item in response.output or []]
            calls = [item for item in output if item["type"] == "computer_call"]
            if not calls:
                if not any(item["type"] == "message" for item in output):
                    raise RuntimeError("Model returned neither actions nor a message")
                return
            if turn == 8 or len(self.actions) + len(calls) > 32:
                raise RuntimeError("Computer action limit exceeded")
            history.extend(output)
            for call in calls:
                history.append(await self.handle(call))
