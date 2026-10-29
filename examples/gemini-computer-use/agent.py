import asyncio
import base64
import json
import os
import sys
from typing import Any

from google import genai
from notte_sdk import NotteClient
from playwright.async_api import Page, ViewportSize, async_playwright
from playwright.async_api import TimeoutError as BrowserTimeout


def key(value: str) -> str:
    aliases = {
        "CTRL": "Control",
        "CMD": "Meta",
        "COMMAND": "Meta",
        "ALT": "Alt",
        "SHIFT": "Shift",
        "ESC": "Escape",
        "ENTER": "Enter",
        "TAB": "Tab",
        "BACKSPACE": "Backspace",
        "SPACE": "Space",
        "DELETE": "Delete",
    }
    return "+".join(aliases.get(part.upper(), part) for part in value.split("+"))


VIEWPORT: ViewportSize = {"width": 1440, "height": 900}


async def fit(page: Page) -> None:
    """Give a new tab the computer viewport. Tabs in the window the first page sized already share it."""
    await page.wait_for_load_state("domcontentloaded", timeout=30_000)
    if await page.evaluate("[innerWidth, innerHeight]") != [VIEWPORT["width"], VIEWPORT["height"]]:
        await page.set_viewport_size(VIEWPORT)


async def execute(page: Page, name: str, args: dict[str, Any]) -> None:
    """Execute browser-only actions. Confirmation requests stop this example."""
    safety = args.get("safety_decision")
    if safety is not None and (not isinstance(safety, dict) or safety.get("decision") not in {"allowed", "regular"}):
        raise PermissionError("Computer action requires approval or was blocked")
    # A tab sharing the sized window has no Playwright viewport of its own.
    size = page.viewport_size or VIEWPORT

    def point(prefix: str = "") -> tuple[int, int]:
        x, y = args[prefix + "x"], args[prefix + "y"]
        if not all(type(n) in (int, float) and 0 <= n <= 999 for n in (x, y)):
            raise ValueError("Invalid computer coordinates")
        return int(x * size["width"] / 1000), int(y * size["height"] / 1000)

    if name in {"click", "double_click", "triple_click", "middle_click", "right_click"}:
        await page.mouse.click(
            *point(),
            button={"middle_click": "middle", "right_click": "right"}.get(name, "left"),
            click_count={"double_click": 2, "triple_click": 3}.get(name, 1),
        )
    elif name in {"move", "mouse_down", "mouse_up"}:
        await page.mouse.move(*point())
        if name == "mouse_down":
            await page.mouse.down()
        elif name == "mouse_up":
            await page.mouse.up()
    elif name == "drag_and_drop":
        start, end = point("start_"), point("end_")
        await page.mouse.move(*start)
        await page.mouse.down()
        try:
            await page.mouse.move(*end, steps=10)
        finally:
            await page.mouse.up()
    elif name == "type":
        await page.keyboard.insert_text(args["text"])
        if args.get("press_enter"):
            await page.keyboard.press("Enter")
    elif name in {"press_key", "key_down", "key_up", "hotkey"}:
        if name == "hotkey":
            await page.keyboard.press("+".join(key(part) for part in args["keys"]))
        else:
            method = {"press_key": page.keyboard.press, "key_down": page.keyboard.down, "key_up": page.keyboard.up}[
                name
            ]
            await method(key(args["key"]))
    elif name == "scroll":
        await page.mouse.move(*point())
        distance = args.get("magnitude_in_pixels", 300)
        if type(distance) not in (int, float) or not 0 <= distance <= 999:
            raise ValueError("Invalid scroll distance")
        dx, dy = {"up": (0, -distance), "down": (0, distance), "left": (-distance, 0), "right": (distance, 0)}[
            args["direction"]
        ]
        await page.mouse.wheel(dx, dy)
    elif name == "navigate":
        if not args["url"].startswith(("https://", "http://")):
            raise ValueError("Only HTTP browser navigation is supported")
        await page.goto(args["url"], wait_until="domcontentloaded", timeout=30_000)
    elif name in {"go_back", "go_forward"}:
        await (page.go_back if name == "go_back" else page.go_forward)(wait_until="domcontentloaded", timeout=30_000)
    elif name == "wait":
        seconds = args.get("seconds", 1)
        if type(seconds) not in (int, float) or not 0 <= seconds <= 5:
            raise ValueError("Wait must be between zero and five seconds")
        await asyncio.sleep(seconds)
    elif name != "take_screenshot":
        raise ValueError("Unsupported computer action")


async def perform(page: Page, name: str, args: dict[str, Any]) -> Page:
    popup = None
    if name in {"click", "double_click", "middle_click", "type", "press_key", "hotkey"}:
        popup = asyncio.create_task(page.context.wait_for_event("page", timeout=1000))
        await asyncio.sleep(0)
    try:
        await execute(page, name, args)
        if popup:
            try:
                destination = await popup
                await fit(destination)
                return destination
            except BrowserTimeout:
                if not popup.done() or popup.exception() is None:
                    raise
        return page
    finally:
        if popup:
            if not popup.done():
                popup.cancel()
            await asyncio.gather(popup, return_exceptions=True)


async def run(task: str, initial_url: str = "https://example.com") -> dict[str, Any]:
    api_key = os.environ["GEMINI_API_KEY"]
    model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    tool = {"type": "computer_use", "environment": "browser", "enable_prompt_injection_detection": True}
    with NotteClient().Session(max_duration_minutes=3) as session:
        async with (
            async_playwright() as driver,
            genai.Client(api_key=api_key, http_options={"timeout": 60_000, "retry_options": {"attempts": 1}}).aio as ai,
        ):
            browser = None
            try:
                browser = await driver.chromium.connect_over_cdp(session.cdp_url())
                page = await browser.contexts[0].new_page()
                await page.set_viewport_size(VIEWPORT)
                await page.goto(initial_url, wait_until="domcontentloaded", timeout=30_000)
                active_page = page

                def opened(destination: Page) -> None:
                    nonlocal active_page
                    active_page = destination

                page.context.on("page", opened)

                async def refresh_page() -> bool:
                    nonlocal page
                    if active_page is page or active_page.is_closed():
                        return False
                    page = active_page
                    await fit(page)
                    return True

                screenshot = base64.b64encode(await page.screenshot()).decode()
                interaction = await ai.interactions.create(
                    model=model,
                    tools=[tool],
                    input=[
                        {"type": "text", "text": task},
                        {"type": "image", "data": screenshot, "mime_type": "image/png"},
                    ],
                )
                actions = 0
                for turn in range(13):
                    changed = await refresh_page()
                    calls = [step for step in interaction.steps if step.type == "function_call"]
                    if not calls:
                        if changed and turn < 12:
                            image = base64.b64encode(await page.screenshot()).decode()
                            interaction = await ai.interactions.create(
                                model=model,
                                tools=[tool],
                                previous_interaction_id=interaction.id,
                                input=[
                                    {
                                        "type": "text",
                                        "text": "A new browser tab opened. Continue the original task using this screenshot.",
                                    },
                                    {"type": "image", "data": image, "mime_type": "image/png"},
                                ],
                            )
                            continue
                        if changed:
                            raise RuntimeError("Computer task exceeded twelve turns")
                        if interaction.status != "completed":
                            raise RuntimeError("Computer task did not complete")
                        answer = " ".join(
                            part.text
                            for step in interaction.steps
                            if step.type == "model_output"
                            for part in step.content
                            if part.type == "text"
                        )
                        return {
                            "answer": answer,
                            "title": await page.title(),
                            "session_id": session.session_id,
                            "actions": actions,
                        }
                    if turn == 12:
                        raise RuntimeError("Computer task exceeded twelve turns")
                    results = []
                    for call in calls:
                        changed = await refresh_page() or changed
                        previous_page = page
                        executed = not changed
                        if executed:
                            page = await perform(page, call.name, call.arguments)
                            actions += 1
                            await refresh_page()
                        state = {"url": page.url}
                        if not executed:
                            state["note"] = (
                                "A new tab opened; this action was not executed. Use the current screenshot."
                            )
                        image = base64.b64encode(await page.screenshot()).decode()
                        results.append(
                            {
                                "type": "function_result",
                                "name": call.name,
                                "call_id": call.id,
                                "result": [
                                    {"type": "text", "text": json.dumps(state)},
                                    {"type": "image", "data": image, "mime_type": "image/png"},
                                ],
                            }
                        )
                        changed = changed or page is not previous_page
                    interaction = await ai.interactions.create(
                        model=model,
                        tools=[tool],
                        previous_interaction_id=interaction.id,
                        input=results,
                    )
                raise RuntimeError("Computer task exceeded twelve turns")
            except PermissionError:
                raise
            except Exception as error:
                code = getattr(error, "status_code", None)
                if isinstance(code, int):
                    raise RuntimeError(f"Gemini API error {code}") from None
                raise RuntimeError("Gemini computer task failed") from None
            finally:
                if browser:
                    failed = sys.exception() is not None
                    try:
                        await asyncio.wait_for(browser.close(), timeout=5)
                    except Exception:
                        if not failed:
                            raise RuntimeError("Gemini browser cleanup failed") from None


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run(" ".join(sys.argv[1:]) or "Go to https://example.com and read its page title."))))
