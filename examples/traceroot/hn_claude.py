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
OPTIONS = ClaudeAgentOptions(
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


@traceroot.observe(name="hacker_news.top_stories", type="agent")
async def top_stories(task: str = TASK) -> dict:
    with NotteClient().Session(max_duration_minutes=5) as session:
        # Group every trace from this browser under its Notte session ID.
        traceroot.update_current_trace(session_id=session.session_id)
        prompt = f"Use Notte tools with browser_id {session.session_id}. {task} Report only what the page shows."
        answer = None
        # Call query through the module: traceroot.initialize() wraps claude_agent_sdk.query.
        async for message in claude_agent_sdk.query(prompt=prompt, options=OPTIONS):
            if isinstance(message, ResultMessage) and not message.is_error:
                answer = message.structured_output
    if not isinstance(answer, dict):
        raise RuntimeError("The Claude agent returned no stories")
    return {**answer, "session_id": session.session_id, "trace_id": traceroot.get_current_trace_id()}


if __name__ == "__main__":
    # Records the agent run, each model call and each Notte tool call.
    traceroot.initialize(integrations=[Integration.CLAUDE_AGENT_SDK])
    try:
        # asyncio.Runner closes the loop on exit, which stops the SDKs' worker threads.
        with asyncio.Runner() as runner:
            print(json.dumps(runner.run(top_stories()), indent=2))
    finally:
        traceroot.shutdown()
