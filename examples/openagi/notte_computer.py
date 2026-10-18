import asyncio
import io
import re
from collections.abc import Awaitable, Callable

from oagi.types.models import Action
from playwright.async_api import Page

KEYS = {
    "enter": "Enter",
    "return": "Enter",
    "tab": "Tab",
    "esc": "Escape",
    "escape": "Escape",
    "ctrl": "Control",
    "control": "Control",
    "alt": "Alt",
    "shift": "Shift",
    "command": "Meta",
    "meta": "Meta",
    "space": "Space",
    "backspace": "Backspace",
    "delete": "Delete",
    "up": "ArrowUp",
    "down": "ArrowDown",
    "left": "ArrowLeft",
    "right": "ArrowRight",
    "home": "Home",
    "end": "End",
    "pageup": "PageUp",
    "pagedown": "PageDown",
}


class Screenshots:
    def __init__(self, page: Page):
        self.page = page
        self.image: bytes | None = None

    async def __call__(self) -> io.BytesIO:
        self.image = await self.page.screenshot(type="png")
        return io.BytesIO(self.image)

    async def last_image(self) -> io.BytesIO:
        return io.BytesIO(self.image) if self.image is not None else await self()


class BrowserActions:
    """Execute approved Lux actions in one browser viewport."""

    def __init__(self, page: Page, *, confirm: Callable[[Action], Awaitable[bool]]):
        if not page.viewport_size:
            raise ValueError("Set an explicit browser viewport")
        self.page = page
        self.confirm = confirm
        self.used = 0

    def point(self, values: list[str]) -> tuple[int, int]:
        if len(values) != 2 or any(not re.fullmatch(r"\d{1,4}", value) for value in values):
            raise ValueError("Expected two normalized coordinates")
        x, y = map(int, values)
        viewport = self.page.viewport_size
        if not viewport or not (0 <= x <= 1000 and 0 <= y <= 1000):
            raise ValueError("Coordinates outside the normalized viewport")
        return round(x * (viewport["width"] - 1) / 1000), round(y * (viewport["height"] - 1) / 1000)

    async def __call__(self, actions: list[Action]) -> None:
        if not actions or len(actions) > 64:
            raise ValueError("Missing actions or action limit exceeded")
        if any(action.type.value in ("fail", "call_user") for action in actions):
            raise PermissionError("Lux stopped for failure or human review")
        if any(action.type.value == "finish" for action in actions[:-1]):
            raise ValueError("Finish must be the last action")
        for action in actions:
            count = action.count or 1
            if count > 8 or self.used + count > 64:
                raise ValueError("Action limit exceeded")
            if not await self.confirm(action):
                raise PermissionError("Computer action refused")
            self.used += count
            kind, argument = action.type.value, action.argument
            values = [part.strip() for part in argument.split(",")]
            for _ in range(count):
                if kind in ("click", "left_double", "left_triple", "right_single"):
                    x, y = self.point(values)
                    await self.page.mouse.click(
                        x,
                        y,
                        button="right" if kind == "right_single" else "left",
                        click_count={"left_double": 2, "left_triple": 3}.get(kind, 1),
                    )
                elif kind == "type":
                    if len(argument) > 4096:
                        raise ValueError("Typed text is too long")
                    await self.page.keyboard.insert_text(argument)
                elif kind == "hotkey":
                    keys = [part.strip().lower() for part in argument.split("+")]
                    if len(keys) > 4 or any(key not in KEYS and not re.fullmatch(r"[a-z0-9]", key) for key in keys):
                        raise ValueError("Unsupported hotkey")
                    await self.page.keyboard.press("+".join(KEYS.get(key, key) for key in keys))
                elif kind == "scroll":
                    x, y = self.point(values[:2])
                    if len(values) != 3 or values[2] not in ("up", "down"):
                        raise ValueError("Unsupported scroll direction")
                    await self.page.mouse.move(x, y)
                    await self.page.mouse.wheel(0, -400 if values[2] == "up" else 400)
                elif kind == "drag":
                    start, end = self.point(values[:2]), self.point(values[2:])
                    await self.page.mouse.move(*start)
                    await self.page.mouse.down()
                    try:
                        await self.page.mouse.move(*end, steps=10)
                    finally:
                        await self.page.mouse.up()
                elif kind == "wait":
                    await asyncio.sleep(1)
                elif kind == "finish":
                    return
                else:
                    raise ValueError("Unsupported Lux action")
