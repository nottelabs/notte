import asyncio
import json
import secrets

from anthropic import AsyncAnthropic
from notte_computer import NotteComputer
from notte_sdk import NotteClient


async def run_demo() -> dict:
    client = NotteClient()
    async with client.Session(max_duration_minutes=3, viewport_width=1024, viewport_height=768) as session:
        try:
            async with asyncio.timeout(120):
                page = await session.apage
                await page.goto("about:blank")
                await page.set_viewport_size({"width": 1024, "height": 768})
                code = "orbit-" + secrets.token_hex(3)
                await page.set_content(
                    '<body style="font:28px Arial;padding:40px"><h1>Copy the code</h1>'
                    f"<p>Code: {code}</p>"
                    "<form onsubmit=\"event.preventDefault();document.querySelector('output').textContent="
                    f"document.querySelector('input').value === '{code}'?'Accepted':'Wrong code'\">"
                    '<label>Code <input style="font-size:28px"></label><button>Submit</button></form>'
                    "<output></output></body>"
                )

                async def confirm(context) -> bool:
                    return page.url == "about:blank"

                calls: list[str] = []
                async with NotteComputer(page, confirm=confirm) as computer, AsyncAnthropic() as provider:
                    runner = provider.beta.messages.tool_runner(
                        model="claude-haiku-5-5",
                        max_tokens=1024,
                        max_iterations=8,
                        tools=[computer],
                        messages=[
                            {
                                "role": "user",
                                "content": "Take a screenshot. Enter the code shown on the page into its form, "
                                "submit using Enter, and report the result. Use only computer tools.",
                            }
                        ],
                    )
                    async for message in runner:
                        calls.extend(block.name for block in message.content if block.type == "tool_use")
                    output = await page.locator("output").inner_text()
                    if output != "Accepted" or await page.locator("input").input_value() != code:
                        raise RuntimeError("The computer agent did not complete the form")
                return {"output": output, "session_id": session.session_id, "calls": calls}
        except Exception:
            raise RuntimeError(f"Computer use failed (session {session.session_id})") from None


if __name__ == "__main__":
    try:
        with asyncio.Runner() as runner:
            print(json.dumps(runner.run(run_demo())))
    except Exception as error:
        print(str(error))
        raise SystemExit(1) from None
