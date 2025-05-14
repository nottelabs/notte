import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from notte_sdk.types import ObserveResponse, ScrapeResponse

# Create server parameters for stdio connection
server_params = StdioServerParameters(
    command="python",  # Executable
    args=["packages/notte-mcp/src/notte_mcp/server.py"],  # Optional command line arguments
    env=None,  # Optional environment variables
)


@pytest.mark.skip(reason="This test is not working on the CI for some reason")
@pytest.mark.asyncio
async def test_start_stop_list_sessions():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize the connection
            await session.initialize()

            # List available prompts
            prompts = await session.list_prompts()

            assert len(prompts.prompts) == 0

            # List available resources
            resources = await session.list_resources()

            assert len(resources.resources) == 0

            # List available tools
            tools = await session.list_tools()

            assert len(tools.tools) == 8

            # Test1: start a new session, list sessions, stop session, list sessions

            # Call a tool
            result = await session.call_tool("notte_start_session", arguments={})
            assert "started" in result.content[0].text

            result = await session.call_tool("notte_list_sessions", arguments={})
            init_len = len(result.content)
            assert init_len > 0

            result = await session.call_tool("notte_stop_session", arguments={})
            assert "stopped" in result.content[0].text

            result = await session.call_tool("notte_list_sessions", arguments={})
            assert len(result.content) == init_len - 1


@pytest.mark.skip(reason="This test is not working on the CI for some reason")
@pytest.mark.asyncio
async def test_observe_step():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Test1: start a new session, list sessions, stop session, list sessions

            # Call a tool
            result = await session.call_tool("notte_observe", arguments={"url": "https://notte.cc"})
            assert len(result.content) == 1
            obs = ObserveResponse.model_validate_json(result.content[0].text).to_obs()
            assert obs.space is not None
            assert len(obs.space.actions) > 0

            # sample a link and take an action
            # action = obs.space.
            result = await session.call_tool("notte_step", arguments={"action_id": "L6"})
            assert len(result.content) == 1
            obs2 = ObserveResponse.model_validate_json(result.content[0].text).to_obs()
            assert obs2.metadata.url != obs.metadata.url


@pytest.mark.skip(reason="This test is not working on the CI for some reason")
@pytest.mark.asyncio
async def test_scrape():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool("notte_scrape", arguments={"url": "https://notte.cc"})
            assert len(result.content) == 1
            data = ScrapeResponse.model_validate_json(result.content[0].text)
            assert data.data is not None


@pytest.mark.skip(reason="This test is not working on the CI for some reason")
@pytest.mark.asyncio
async def test_scrape_with_agent():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool(
                "notte_operator",
                arguments={"task": "go to notte.cc and scrape the pricing plans", "url": "https://notte.cc"},
            )
            assert len(result.content) == 1
