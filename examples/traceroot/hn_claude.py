import asyncio
import json
import os

import claude_agent_sdk
import traceroot
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage
from notte_sdk import NotteClient
from traceroot import Integration

TASK = "Visit https://news.ycombinator.com and return the top 3 stories with their points."
SCHEMA = {
    "type": "object",
    "properties": {
        "stories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"title": {"type": "string"}, "points": {"type": "integer"}},
                "required": ["title", "points"],
            },
        }
    },
    "required": ["stories"],
}


@traceroot.observe(name="hacker_news.top_stories", type="agent", capture_input=False)
async def top_stories(session_id: str) -> dict:
    traceroot.update_current_span(input={"task": TASK})
    options = ClaudeAgentOptions(
        model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5"),
        tools=[],
        setting_sources=[],
        strict_mcp_config=True,
        permission_mode="dontAsk",
        allowed_tools=[f"mcp__notte__{name}" for name in ("browser_action", "browser_observe", "browser_scrape")],
        mcp_servers={
            "notte": {
                "type": "http",
                "url": (os.environ.get("NOTTE_API_URL") or "https://api.notte.cc").rstrip("/") + "/mcp",
                # The SDK fills in ${NOTTE_API_KEY} from the environment.
                "headers": {"Authorization": "Bearer ${NOTTE_API_KEY}"},
            }
        },
        max_turns=10,
        output_format={"type": "json_schema", "schema": SCHEMA},
    )
    answer = None
    try:
        # Call query through the module: traceroot.initialize() wraps claude_agent_sdk.query.
        async for message in claude_agent_sdk.query(
            prompt=f"Use Notte tools with browser_id {session_id}. {TASK} Report only what the page shows.",
            options=options,
        ):
            if isinstance(message, ResultMessage) and not message.is_error:
                answer = message.structured_output
        if not isinstance(answer, dict):
            raise RuntimeError("The Claude agent returned no stories")
    except Exception:
        # Raw errors can quote request details, so the span records only the session.
        raise RuntimeError(f"Claude agent failed (session {session_id})") from None
    return {**answer, "trace_id": traceroot.get_current_trace_id()}


async def main() -> dict:
    with NotteClient().Session(max_duration_minutes=5) as session:
        # Group every trace from this browser under its Notte session ID.
        with traceroot.using_attributes(session_id=session.session_id):
            result = await top_stories(session.session_id)
        return {**result, "session_id": session.session_id}


if __name__ == "__main__":
    # Records the agent run, each model call and each Notte tool call.
    traceroot.initialize(integrations=[Integration.CLAUDE_AGENT_SDK])
    try:
        # asyncio.Runner closes the loop on exit, which stops the SDKs' worker threads.
        with asyncio.Runner() as runner:
            print(json.dumps(runner.run(main()), indent=2))
    finally:
        traceroot.shutdown()
