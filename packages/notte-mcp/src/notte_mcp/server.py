import os
import pathlib
from collections.abc import Sequence
from typing import Annotated, Final, Literal

from dotenv import load_dotenv
from loguru import logger
from mcp.server.fastmcp import FastMCP, Image
from notte_agent.falco.perception import FalcoPerception
from notte_core.actions import ActionUnion
from notte_core.browser.observation import ExecutionResult, TrajectoryProgress
from notte_core.common.config import PerceptionType
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
session: RemoteSession | None = None
current_step: int = 0

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

notte = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))

# Create an MCP server
mcp = FastMCP(
    name="Notte MCP Server for Notte Browser Sessions and Web Agents Operators",
    request_timeout=NOTTE_MCP_MAX_AGENT_WAIT_TIME,
    # TOOD: coment out this line for local testing
    dependencies=[f"notte-sdk=={__version__}", "mcp[cli]>=1.6.0"],
    port=8001,
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


def reset_session() -> RemoteSession:
    global session
    global current_step
    session = None
    current_step = 0
    session = notte.Session(
        viewport_width=DEFAULT_HEADLESS_VIEWPORT_WIDTH,
        viewport_height=DEFAULT_HEADLESS_VIEWPORT_HEIGHT,
        perception_type=PerceptionType.FAST,
    )
    session.start()
    return session


def get_session() -> RemoteSession:
    global session
    if session is None:
        return reset_session()

    response = session.status()
    if response.status != "active":
        return reset_session()
    return session


@mcp.tool(description="Health check the Notte MCP server")
def notte_health_check() -> str:
    """Health check the Notte MCP server"""
    return "Notte MCP server is healthy"


@mcp.tool(description="Start a new cloud browser session using Notte")
def notte_start_session() -> str:
    """Start a new Notte session"""
    session = get_session()
    return f"Session {session.session_id} started"


@mcp.tool(description="List all Notte Cloud Browser active sessions")
def notte_list_sessions() -> Sequence[SessionResponse]:
    """List all active Notte sessions"""
    return notte.sessions.list(only_active=True)


@mcp.tool(description="Get the current Notte session status")
def notte_get_session_status() -> str:
    """Get the current Notte session status"""
    session = get_session()
    status = session.status()
    return f"Session {session.session_id} is {status.status} (started at {status.created_at} and last accessed at {status.last_accessed_at})"


@mcp.tool(description="Stop the current Notte session")
def notte_stop_session() -> str:
    """Stop the current Notte session"""
    _session = get_session()
    _session.stop()
    global session
    session = None
    return f"Session {_session.session_id} stopped"


@mcp.tool(
    description="Takes a screenshot of the current page. Use this tool to learn where you are on the page when navigating. Only use this tool when the other tools are not sufficient to get the information you need."
)
def notte_screenshot() -> Image:
    """Takes a screenshot of the current page"""
    session = get_session()
    response = session.observe(perception_type=PerceptionType.FAST)
    return Image(
        data=response.screenshot.bytes(),
        format="png",
    )


@mcp.tool(
    description="Observes elements on the web page. Use this tool to observe elements that you can later use in an action. Use observe instead of extract when dealing with actionable (interactable) elements rather than text."
)
def notte_observe() -> ObservationToolResponse:
    """Observe the current page and the available actions on it"""
    session = get_session()
    obs = session.observe(perception_type=PerceptionType.FAST)
    progress = TrajectoryProgress(current_step=current_step, max_steps=30)

    return ObservationToolResponse(
        observation=FalcoPerception(with_disclaimer=False).perceive(obs=obs, progress=progress),
        code="session.observe()",
    )


@mcp.tool(description="Scrape the current page data")
def notte_scrape(
    instructions: Annotated[
        str | None,
        "Additional instructions to use for the scrape (i.e specific fields or information to extract). If None, the current page will be scraped as a markdown string.",
    ] = None,
) -> str | BaseModel:
    """Scrape the current page data"""
    session = get_session()
    data = session.scrape(instructions=instructions)
    global current_step
    current_step += 1
    if instructions:
        assert data.structured is not None
        return data.structured
    assert data.markdown is not None
    return data.markdown


@mcp.tool(
    description="Take an action on the current page. Use `notte_observe` first to list the available actions. Then use this tool to take an action. Don't hallucinate any action not listed in the observation."
)
def notte_execute(
    action: ActionUnion,
) -> ExecutionToolResponse:
    """Take an action on the current page"""
    session = get_session()
    result = session.execute(action=action)
    global current_step
    current_step += 1
    return ExecutionToolResponse(
        result=result,
        code=f"session.execute({result.action.model_dump_agent(include_selector=True)}, raise_exception_on_failure=True)",
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
    session = get_session()
    agent = notte.Agent(session=session)
    _ = agent.start(task=task, url=url)
    if vizualize_in_browser:
        session.viewer()
    # wait for the agent to finish
    response = await agent.watch_logs_and_wait()
    global current_step
    current_step += len(response.steps)
    if response.success:
        assert response.answer is not None
        return response.answer
    else:
        return f"Failed to run agent with error: {response.answer}. Try to be better specify the task and url."


if __name__ == "__main__":
    # set the environment variable to the protocol: NOTTE_MCP_SERVER_PROTOCOL = "sse" or "stdio"
    mcp.run(transport=NOTTE_MCP_SERVER_PROTOCOL)
