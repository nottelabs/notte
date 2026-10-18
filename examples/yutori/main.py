import asyncio
import json
from contextlib import AsyncExitStack, asynccontextmanager
from urllib.parse import urlsplit

from notte_sdk import NotteClient
from openai import APIStatusError
from playwright.async_api import Page, async_playwright
from yutori import AsyncYutoriClient
from yutori.navigator import (
    N1_5_MODEL,
    TOOL_SET_CORE,
    acreate_trimmed,
    aplaywright_screenshot_to_data_url,
    denormalize_coordinates,
    map_key_to_playwright,
)


class BrowserTaskError(RuntimeError):
    pass


ACTIONS = {"left_click", "type", "key_press", "scroll", "goto_url", "go_back", "go_forward", "refresh", "wait"}
DISABLED = [
    "double_click",
    "triple_click",
    "right_click",
    "middle_click",
    "mouse_down",
    "mouse_up",
    "mouse_move",
    "drag",
    "hold_key",
]


async def act(page: Page, name: str, arguments: dict):
    if name not in ACTIONS:
        raise BrowserTaskError("Yutori returned an unsupported browser action")
    held = []
    try:
        for key in map_key_to_playwright(arguments["modifier"]) if arguments.get("modifier") else []:
            await page.keyboard.down(key)
            held.append(key)
        if name in {"left_click", "scroll"}:
            coordinates = arguments["coordinates"]
            viewport = await page.evaluate("({width:innerWidth,height:innerHeight})")
            x, y = denormalize_coordinates(coordinates, viewport["width"], viewport["height"])
            await page.mouse.move(x, y)
            if name == "left_click":
                await page.mouse.click(x, y)
            else:
                distance = min(max(float(arguments.get("amount", 3)), 0), 20) * 100
                directions = {
                    "up": (0, -distance),
                    "down": (0, distance),
                    "left": (-distance, 0),
                    "right": (distance, 0),
                }
                await page.mouse.wheel(*directions[arguments.get("direction", "down")])
        elif name == "type":
            await page.keyboard.insert_text(arguments["text"])
        elif name == "key_press":
            for key in map_key_to_playwright(arguments["key"]):
                await page.keyboard.press(key)
        elif name == "goto_url":
            url = arguments["url"]
            if urlsplit(url).scheme not in {"http", "https"}:
                raise ValueError("Only HTTP navigation is supported")
            await page.goto(url, wait_until="domcontentloaded", timeout=15_000)
        elif name == "wait":
            await asyncio.sleep(min(max(float(arguments.get("duration", 1)), 0), 10))
        else:
            await {"go_back": page.go_back, "go_forward": page.go_forward, "refresh": page.reload}[name](
                wait_until="domcontentloaded", timeout=15_000
            )
    except Exception:
        raise BrowserTaskError(f"Yutori browser action failed: {name}") from None
    finally:
        try:
            for key in reversed(held):
                await page.keyboard.up(key)
        except Exception:
            raise BrowserTaskError("Yutori keyboard cleanup failed") from None


async def _finish_owned(task):
    cancelled = False
    while True:
        try:
            return await asyncio.shield(task), cancelled
        except asyncio.CancelledError:
            if task.cancelled():
                raise
            cancelled = True


@asynccontextmanager
async def owned_connection():
    session = NotteClient().Session(max_duration_minutes=3, proxies=False, viewport_width=1280, viewport_height=800)
    entered = False
    primary = None
    try:
        _, cancelled = await _finish_owned(asyncio.create_task(session.__aenter__()))
        entered = True
        if cancelled:
            raise asyncio.CancelledError
        endpoint = await asyncio.to_thread(session.cdp_url)
        yield session, endpoint
    except BaseException as error:
        primary = error
        if isinstance(error, Exception) and not isinstance(error, BrowserTaskError):
            primary = BrowserTaskError("Yutori browser connection failed")
            raise primary from None
        raise
    finally:
        if entered or session.response is not None:
            try:
                _, cancelled = await _finish_owned(
                    asyncio.create_task(
                        asyncio.to_thread(session.stop, close_reason="error" if primary is not None else "manual")
                    )
                )
            except Exception:
                if primary is None:
                    raise BrowserTaskError("Yutori browser cleanup failed") from None
                primary.add_note("Yutori browser cleanup failed")
            else:
                if cancelled and primary is None:
                    raise asyncio.CancelledError


async def run(
    task: str, start_url: str = "https://example.com", *, max_steps: int = 12, client: AsyncYutoriClient | None = None
):
    if not 1 <= max_steps <= 30:
        raise ValueError("Choose max_steps between 1 and 30")
    async with AsyncExitStack() as resources:
        if client is None:
            client = await resources.enter_async_context(AsyncYutoriClient(timeout=30))
        async with owned_connection() as (session, endpoint):
            step = "browser connection"
            try:
                async with async_playwright() as playwright:
                    browser = await playwright.chromium.connect_over_cdp(endpoint)
                    failed = False
                    try:
                        page = await browser.contexts[0].new_page()
                        await act(page, "goto_url", {"url": start_url})
                        messages = [{"role": "user", "content": task}]
                        for _ in range(max_steps):
                            step = "screenshot"
                            image = await aplaywright_screenshot_to_data_url(page)
                            messages.append(
                                {"role": "user", "content": [{"type": "image_url", "image_url": {"url": image}}]}
                            )
                            step = "model request"
                            response = await acreate_trimmed(
                                client.chat.completions,
                                messages,
                                model=N1_5_MODEL,
                                tool_set=TOOL_SET_CORE,
                                disable_tools=DISABLED,
                            )
                            message = response.choices[0].message
                            messages.append(message.model_dump(exclude_none=True))
                            if not message.tool_calls:
                                if response.choices[0].finish_reason != "stop":
                                    raise BrowserTaskError("Yutori response ended before completion")
                                return {"answer": message.content, "session_id": session.session_id}
                            for tool in message.tool_calls:
                                step = "browser action"
                                await act(page, tool.function.name, json.loads(tool.function.arguments))
                                messages.append(
                                    {"role": "tool", "tool_call_id": tool.id, "content": "Action completed"}
                                )
                        raise BrowserTaskError("Yutori step limit reached")
                    except BaseException:
                        failed = True
                        raise
                    finally:
                        try:
                            await asyncio.wait_for(browser.close(), timeout=5)
                        except Exception:
                            if not failed:
                                raise BrowserTaskError("Yutori browser disconnect failed") from None
            except APIStatusError as error:
                raise BrowserTaskError(f"Yutori {step} failed (HTTP {error.status_code})") from None
            except Exception as error:
                if isinstance(error, BrowserTaskError):
                    raise
                raise BrowserTaskError(f"Yutori {step} failed") from None


if __name__ == "__main__":
    print(asyncio.run(run("Read the page title and report it.")))
