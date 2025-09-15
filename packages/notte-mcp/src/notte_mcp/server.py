import asyncio
import os
import pathlib
from collections.abc import Sequence
from contextlib import asynccontextmanager
from typing import Annotated, Final, Literal

from dotenv import load_dotenv
from loguru import logger
from mcp.server.fastmcp import FastMCP, Image
from notte_core.actions import ActionUnion
from notte_core.browser.observation import ExecutionResult
from notte_core.browser.perception import ObservationPerception
from notte_core.data.space import StructuredData
from notte_core.utils.pydantic_schema import JsonResponseFormat, convert_response_format_to_pydantic_model
from notte_sdk import NotteClient, __version__
from notte_sdk.endpoints.sessions import RemoteSession
from notte_sdk.types import (
    DEFAULT_HEADLESS_VIEWPORT_HEIGHT,
    DEFAULT_HEADLESS_VIEWPORT_WIDTH,
    SessionResponse,
)
from pydantic import BaseModel

# #########################################################
# ####################### CONFIG ##########################
# #########################################################

_ = load_dotenv()


mcp_server_path = pathlib.Path(__file__).absolute()

# Global state with proper synchronization
_session_lock = asyncio.Lock()
session: RemoteSession | None = None
current_step: int = 0
_initialization_complete = asyncio.Event()

os.environ["NOTTE_MCP_SERVER_PATH"] = str(mcp_server_path)

NOTTE_MCP_SERVER_PROTOCOL: Final[Literal["sse", "stdio"]] = os.getenv("NOTTE_MCP_SERVER_PROTOCOL", "sse")  # type: ignore
if NOTTE_MCP_SERVER_PROTOCOL not in ["sse", "stdio"]:
    raise ValueError(f"Invalid protocol: {NOTTE_MCP_SERVER_PROTOCOL}. Valid protocols are 'sse' and 'stdio'.")
NOTTE_MCP_MAX_AGENT_WAIT_TIME: Final[int] = int(os.getenv("NOTTE_MCP_MAX_AGENT_WAIT_TIME", 120))
NOTTE_API_URL: Final[str] = os.getenv("NOTTE_API_URL", "https://api.notte.cc")

logger.info(f"""
#######################################
############## NOTTE MCP ##############
#######################################
notte-sdk version  : {__version__}
protocol           : {NOTTE_MCP_SERVER_PROTOCOL}
max agent wait time: {NOTTE_MCP_MAX_AGENT_WAIT_TIME}
path               : {mcp_server_path}
api url            : {NOTTE_API_URL}
########################################
########################################
########################################
""")


@asynccontextmanager
async def lifespan(_app: object):
    """Lifespan context manager for proper initialization"""
    # Startup
    logger.info("Starting MCP server initialization...")
    try:
        global notte
        notte = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))
        notte.health_check()
        logger.info("Notte client initialized successfully")
        _ = _initialization_complete.set()
        logger.info("MCP server initialization complete")
        yield
    except Exception as e:
        logger.error(f"Failed to initialize MCP server: {e}")
        raise
    finally:
        # Shutdown
        logger.info("Shutting down MCP server...")
        global session
        if session:
            try:
                session.stop()
            except Exception as e:
                logger.warning(f"Error stopping session during shutdown: {e}")


# Global notte client - will be initialized during startup
notte: NotteClient

# Create an MCP server with lifespan management
mcp = FastMCP(
    name="Notte MCP Server for Notte Browser Sessions and Web Agents Operators",
    request_timeout=NOTTE_MCP_MAX_AGENT_WAIT_TIME,
    # TOOD: coment out this line for local testing
    dependencies=[f"notte-sdk=={__version__}", "mcp[cli]>=1.6.0"],
    port=8001,
    lifespan=lifespan,
)

# #########################################################
# ######################## Models #########################
# #########################################################


class ObservationToolResponse(BaseModel):
    observation: str
    code: str


class ExecutionToolResponse(BaseModel):
    result: ExecutionResult
    code: str


# #########################################################
# ######################## TOOLS ##########################
# #########################################################


def _create_new_session() -> RemoteSession:
    """Helper function to create a new session"""
    global session, current_step

    # Stop old session if it exists (ignore failures)
    if session:
        try:
            session.stop()
        except Exception:
            pass  # Ignore stop failures - we're creating a new session anyway

    session = notte.Session(
        viewport_width=DEFAULT_HEADLESS_VIEWPORT_WIDTH,
        viewport_height=DEFAULT_HEADLESS_VIEWPORT_HEIGHT,
        perception_type="fast",
        raise_on_failure=False,
    )
    session.start()
    current_step = 0
    logger.info(f"New session started: {session.session_id}")
    return session


async def get_session() -> RemoteSession:
    """Get current session with proper synchronization"""
    global session

    # Wait for initialization to complete
    _ = await _initialization_complete.wait()

    async with _session_lock:
        if session is None:
            return _create_new_session()

    response = session.status()
    if response.status != "active":
        return _create_new_session()
    return session


@mcp.tool(description="Health check the Notte MCP server")
async def notte_health_check() -> str:
    """Health check the Notte MCP server"""
    return "Notte MCP server is healthy"


@mcp.tool(description="Start a new cloud browser session using Notte")
async def notte_start_session() -> str:
    """Start a new Notte session"""
    session = await get_session()
    return f"Session {session.session_id} started"


@mcp.tool(description="List all Notte Cloud Browser active sessions")
async def notte_list_sessions() -> Sequence[SessionResponse]:
    """List all active Notte sessions"""
    _ = await _initialization_complete.wait()
    return notte.sessions.list(only_active=True)


@mcp.tool(description="Get the current Notte session status")
async def notte_get_session_status() -> str:
    """Get the current Notte session status"""
    session = await get_session()
    status = session.status()
    return f"Session {session.session_id} is {status.status} (started at {status.created_at} and last accessed at {status.last_accessed_at})"


@mcp.tool(description="Stop the current Notte session")
async def notte_stop_session() -> str:
    """Stop the current Notte session"""
    global session
    async with _session_lock:
        if session:
            session_id = session.session_id
            session.stop()
            session = None
            return f"Session {session_id} stopped"
        else:
            return "No active session to stop"


@mcp.tool(
    description="Takes a screenshot of the current page. Use this tool to learn where you are on the page when navigating. Only use this tool when the other tools are not sufficient to get the information you need."
)
async def notte_screenshot() -> Image:
    """Takes a screenshot of the current page"""
    session = await get_session()
    response = session.observe(perception_type="fast")
    return Image(
        data=response.screenshot.bytes(),
        format="png",
    )


@mcp.tool(
    description="Observes elements on the web page. Use this tool to observe elements that you can later use in an action. Use observe instead of extract when dealing with actionable (interactable) elements rather than text."
)
async def notte_observe() -> ObservationToolResponse:
    """Observe the current page and the available actions on it"""
    session = await get_session()
    obs = session.observe(perception_type="fast")

    return ObservationToolResponse(
        observation=ObservationPerception().perceive(obs=obs),
        code="session.observe()",
    )


@mcp.tool(description="Scrape the current page data")
async def notte_scrape(
    response_format: Annotated[
        JsonResponseFormat | None,
        "The response format to use for the scrape. If None and no instructions are provided, the full current page will be scraped as a markdown string (useful for debugging).",
    ] = None,
    instructions: Annotated[
        str | None,
        "Additional instructions to use for the scrape (i.e specific fields or information to extract). You can use that with `response_format=None` first to try to extract some data from the page from a rough natural language description. If None and no response format is provided, the full current page will be scraped as a markdown string (useful for debugging).",
    ] = None,
) -> str | StructuredData[BaseModel]:
    """Scrape the current page data"""
    global current_step
    session = await get_session()
    async with _session_lock:
        current_step += 1
    match response_format, instructions:
        case None, None:
            return session.scrape()
        case None, _:
            return session.scrape(instructions=instructions)
        case _, _:
            try:
                _response_format = convert_response_format_to_pydantic_model(response_format.model_dump())
            except Exception as e:
                return f"Error converting response format to pydantic model: {e}"
            assert _response_format is not None, (
                f"Error converting response format to pydantic model: {response_format.model_dump_json()}"
            )
            return session.scrape(instructions=instructions, response_format=_response_format)


@mcp.tool(
    description="Take an action on the current page. Use `notte_observe` first to list the available actions. Then use this tool to take an action. Don't hallucinate any action not listed in the observation."
)
async def notte_execute(
    action: ActionUnion,
) -> ExecutionToolResponse:
    """Take an action on the current page"""
    session = await get_session()
    result = session.execute(action=action)
    global current_step
    async with _session_lock:
        current_step += 1
    return ExecutionToolResponse(
        result=result,
        code=f"session.execute({result.action.model_dump_agent(include_selector=True)}, raise_on_failure=True)",
    )


@mcp.tool(description="Run an `Notte` agent/operator to complete a given task on any website")
async def notte_operator(
    task: Annotated[str, "The task to complete"],
    url: Annotated[str | None, "The URL to complete the task on (optional)"] = None,
    vizualize_in_browser: Annotated[
        bool,
        "Whether to visualize the agent's work in the browser (should only be set to True if explicitely requested by the user otherwise set it to False by default)",
    ] = False,
) -> str:
    """Run an agent asynchronously"""
    session = await get_session()
    agent = notte.Agent(session=session)
    _ = agent.start(task=task, url=url)
    if vizualize_in_browser:
        session.viewer()
    # wait for the agent to finish
    response = await agent.watch_logs_and_wait()
    global current_step
    async with _session_lock:
        current_step += len(response.steps)
    if response.success:
        assert response.answer is not None
        return response.answer
    else:
        return f"Failed to run agent with error: {response.answer}. Try to be better specify the task and url."


if __name__ == "__main__":
    # set the environment variable to the protocol: NOTTE_MCP_SERVER_PROTOCOL = "sse" or "stdio"
    mcp.run(transport=NOTTE_MCP_SERVER_PROTOCOL)
