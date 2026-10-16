# @sniptest filename=notte_claude_agent.py
# @sniptest typecheck_only=true
import asyncio
import os

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
from notte_sdk import NotteClient


async def main() -> dict[str, str]:
    with NotteClient().Session(max_duration_minutes=3) as session:
        options = ClaudeAgentOptions(
            model="claude-haiku-5-5",
            tools=[],
            setting_sources=[],
            strict_mcp_config=True,
            permission_mode="dontAsk",
            allowed_tools=[f"mcp__notte__{name}" for name in ("browser_action", "browser_observe", "browser_scrape")],
            mcp_servers={
                "notte": {
                    "type": "http",
                    "url": os.environ.get("NOTTE_API_URL", "https://api.notte.cc").rstrip("/") + "/mcp",
                    "headers": {"Authorization": "Bearer ${NOTTE_API_KEY}"},
                }
            },
            max_turns=8,
            output_format={
                "type": "json_schema",
                "schema": {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]},
            },
        )
        title: str | None = None
        try:
            async for message in query(
                prompt=f"Use Notte tools with browser_id {session.session_id}. Visit https://example.com and read its page title.",
                options=options,
            ):
                if isinstance(message, ResultMessage) and not message.is_error:
                    if isinstance(message.structured_output, dict):
                        title = message.structured_output.get("title")
            if not isinstance(title, str):
                raise RuntimeError("The Claude agent returned no page title")
        except Exception:
            raise RuntimeError(f"Claude agent failed (session {session.session_id})") from None
        print(title)
        return {"title": title, "session_id": session.session_id}


with asyncio.Runner() as runner:
    result = runner.run(main())
