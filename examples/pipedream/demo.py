import asyncio
import json
import os
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult
from notte_sdk import NotteClient


@dataclass(frozen=True)
class PipedreamConfig:
    client_id: str
    client_secret: str
    project_id: str
    external_user_id: str
    app: str = "github"


def load_action(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    try:
        with open(path) as file:
            value = json.load(file)
        if (
            not isinstance(value, dict)
            or set(value) != {"name", "arguments"}
            or not isinstance(value["name"], str)
            or not value["name"].strip()
            or not isinstance(value["arguments"], dict)
        ):
            raise ValueError()
        return value
    except Exception:
        raise ValueError("Action file must contain a tool name and arguments object") from None


async def connect(stack: AsyncExitStack, url: str, headers: dict[str, str]) -> ClientSession:
    http = await stack.enter_async_context(httpx2.AsyncClient(headers=headers, timeout=20, follow_redirects=False))
    streams = await stack.enter_async_context(streamable_http_client(url, http_client=http))
    client = await stack.enter_async_context(ClientSession(*streams, read_timeout_seconds=20))
    await client.initialize()
    return client


def tool_data(result: Any) -> Any:
    value = result.model_dump(by_alias=True)
    if value.get("isError"):
        raise RuntimeError("Browser tool failed")
    if value.get("structuredContent") is not None:
        return value["structuredContent"]
    text = next(item["text"] for item in value["content"] if item["type"] == "text")
    return json.loads(text)


async def discover(
    config: PipedreamConfig,
    session_id: str,
    oauth_url: str,
    mcp_url: str,
    page_url: str,
    approved_action: dict[str, Any] | None,
) -> dict[str, Any]:
    completed = False
    async with asyncio.timeout(90), AsyncExitStack() as stack:
        api = os.environ.get("NOTTE_API_URL", "https://api.notte.cc").rstrip("/")
        notte = await connect(
            stack,
            f"{api}/mcp",
            {
                "Authorization": f"Bearer {os.environ['NOTTE_API_KEY']}",
            },
        )
        action = tool_data(
            await notte.call_tool(
                "browser_action",
                {
                    "browser_id": session_id,
                    "action": {"type": "goto", "url": page_url},
                },
            )
        )
        if action.get("success") is not True:
            raise RuntimeError("Browser navigation failed")
        page = tool_data(await notte.call_tool("browser_scrape", {"browser_id": session_id}))
        oauth = await stack.enter_async_context(httpx2.AsyncClient(timeout=20, follow_redirects=False))
        response = await oauth.post(
            oauth_url,
            json={
                "grant_type": "client_credentials",
                "client_id": config.client_id,
                "client_secret": config.client_secret,
            },
        )
        if response.status_code != 200:
            raise RuntimeError(f"Pipedream OAuth HTTP {response.status_code}")
        token = response.json()["access_token"]
        if not isinstance(token, str) or not token:
            raise RuntimeError("Pipedream OAuth returned no access token")
        pipedream = await connect(
            stack,
            mcp_url,
            {
                "Authorization": f"Bearer {token}",
                "x-pd-project-id": config.project_id,
                "x-pd-environment": "development",
                "x-pd-external-user-id": config.external_user_id,
                "x-pd-app-slug": config.app,
            },
        )
        tools = (await pipedream.list_tools()).tools
        names = [tool.name for tool in tools]
        if approved_action is not None:
            if approved_action["name"] not in names:
                raise RuntimeError("Approved tool was not offered")
            output = await pipedream.call_tool(approved_action["name"], approved_action["arguments"])
            if not isinstance(output, CallToolResult) or output.is_error:
                raise RuntimeError("Approved tool did not complete successfully")
            # Provider output can contain account links or private data; do not return or log it.
        result = {
            "session_id": session_id,
            "page": page,
            "tool_names": names,
            "tool_call_completed": approved_action is not None,
        }
        completed = True
    task = asyncio.current_task()
    if not completed or (task is not None and task.cancelling()):
        raise asyncio.CancelledError()
    return result


async def run_demo(
    config: PipedreamConfig,
    *,
    oauth_url: str = "https://api.pipedream.com/v1/oauth/token",
    mcp_url: str = "https://remote.mcp.pipedream.net/v3",
    page_url: str = "https://example.com",
    approved_action: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with NotteClient().Session(max_duration_minutes=3) as browser:
        session_id = browser.session_id
        try:
            return await discover(config, session_id, oauth_url, mcp_url, page_url, approved_action)
        except asyncio.CancelledError:
            raise asyncio.CancelledError(f"Pipedream discovery cancelled (session {session_id})") from None
        except Exception as error:
            # Sanitize before the SDK context logs the exception during cleanup.
            raise RuntimeError(f"Pipedream discovery failed: {type(error).__name__} (session {session_id})") from None


if __name__ == "__main__":
    config = PipedreamConfig(
        client_id=os.environ["PIPEDREAM_CLIENT_ID"],
        client_secret=os.environ["PIPEDREAM_CLIENT_SECRET"],
        project_id=os.environ["PIPEDREAM_PROJECT_ID"],
        external_user_id=os.environ["PIPEDREAM_EXTERNAL_USER_ID"],
        app=os.environ.get("PIPEDREAM_APP", "github"),
    )
    with asyncio.Runner() as runner:
        result = runner.run(run_demo(config, approved_action=load_action(os.environ.get("PIPEDREAM_ACTION_FILE"))))
    print(
        json.dumps(
            {
                "session_id": result["session_id"],
                "tool_count": len(result["tool_names"]),
                "tool_call_completed": result["tool_call_completed"],
            }
        )
    )
