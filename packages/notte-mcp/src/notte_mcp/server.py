import os
import pathlib
from collections.abc import Sequence
from typing import Annotated

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP, Image
from notte_sdk import NotteClient, __version__
from notte_sdk.types import ObserveResponse, ScrapeResponse, SessionResponse

_ = load_dotenv()

mcp_server_path = pathlib.Path(__file__).absolute()
session: SessionResponse | None = None

os.environ["NOTTE_MCP_SERVER_PATH"] = str(mcp_server_path)

MAX_AGENT_WAIT_TIME = 120

notte = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))

# Create an MCP server
mcp = FastMCP(
    name="Notte MCP Server for Notte Browser Sessions and Web Agents Operators",
    request_timeout=MAX_AGENT_WAIT_TIME,
    # TOOD: coment out this line for local testing
    dependencies=[f"notte-sdk=={__version__}", "mcp[cli]>=1.6.0"],
)


def get_session_id() -> str:
    global session
    if session is None:
        response = notte.sessions.start()
        session = response
    return session.session_id


@mcp.tool(description="Start a new cloud browser session using Notte")
def notte_start_session() -> str:
    """Start a new Notte session"""
    response = notte.sessions.start()
    global session
    session = response
    return f"Session {session.session_id} started"


@mcp.tool(description="List all Notte Cloud Browser active sessions")
def notte_list_sessions() -> Sequence[SessionResponse]:
    """List all active Notte sessions"""
    return notte.sessions.list(only_active=True)


@mcp.tool(description="Stop the current Notte session")
def notte_stop_session() -> str:
    """Stop the current Notte session"""
    session_id = get_session_id()
    _ = notte.sessions.stop(session_id=session_id)
    global session
    session = None
    return f"Session {session_id} stopped"


@mcp.tool(
    description="Takes a screenshot of the current page. Use this tool to learn where you are on the page when navigating. Only use this tool when the other tools are not sufficient to get the information you need."
)
def notte_screenshot() -> Image:
    """Takes a screenshot of the current page"""
    session_id = get_session_id()
    response = notte.sessions.page.observe(session_id=session_id)
    assert response.screenshot is not None
    return Image(
        data=response.screenshot,
        format="png",
    )


@mcp.tool(
    description="Observes elements on the web page. Use this tool to observe elements that you can later use in an action. Use observe instead of extract when dealing with actionable (interactable) elements rather than text."
)
def notte_observe(
    url: Annotated[
        str | None,
        "The URL of the webpage to observe. If not provided, the current page in the Notte Browser Session will be observed.",
    ] = None,
) -> ObserveResponse:
    """Observe the current page and the available actions on it"""
    session_id = get_session_id()
    response = notte.sessions.page.observe(session_id=session_id, url=url)
    response.screenshot = None
    assert session is not None
    return ObserveResponse.from_obs(response, session=session)


@mcp.tool(description="Scrape the current page data")
def notte_scrape(
    url: Annotated[
        str | None,
        "The URL of the webpage scrape. If not provided, the current page in the Notte Browser Session will be scraped.",
    ] = None,
    instructions: Annotated[
        str | None, "Additional instructions to use for the scrape (i.e specific fields or information to extract)."
    ] = None,
) -> ScrapeResponse:
    """Scrape the current page data"""
    session_id = get_session_id()
    data = notte.sessions.page.scrape(session_id=session_id, url=url, instructions=instructions, use_llm=True)
    assert session is not None
    return ScrapeResponse(
        data=data,
        session=session,
    )


@mcp.tool(
    description="Take an action on the current page. Use `notte_observe` first to list the available actions. Then use this tool to take an action. Don't hallucinate any action not listed in the observation."
)
def notte_step(
    action_id: Annotated[str, "The ID of the action to execute. Use `notte_observe` to list the available actions."],
    value: Annotated[
        str | None,
        "The value to input for form actions. Only to be provider for interactions actions (i.e ID starts with `I`, e.g. `I0`, `I1`, etc.)",
    ] = None,
) -> ObserveResponse:
    """Take an action on the current page"""
    session_id = get_session_id()
    obs = notte.sessions.page.step(session_id=session_id, action_id=action_id, value=value)
    obs.screenshot = None
    assert session is not None
    return ObserveResponse.from_obs(obs, session=session)


@mcp.tool(description="Run an `Notte` agent/operator to complete a given task on any website")
def notte_operator(
    task: Annotated[str, "The task to complete"],
    url: Annotated[str | None, "The URL to complete the task on (optional)"] = None,
    vizualize_in_browser: Annotated[
        bool,
        "Whether to visualize the agent's work in the browser (should only be set to True if explicitely requested by the user otherwise set it to False by default)",
    ] = False,
) -> str:
    """Run an agent asynchronously"""
    agent = notte.agents.start(task=task, url=url)
    if vizualize_in_browser:
        notte.sessions.viewer(session_id=agent.session_id)
    # wait for the agent to finish
    response = notte.agents.wait(agent.agent_id)
    if response.success:
        assert response.answer is not None
        return response.answer
    else:
        return "Failed to run agent. Try to be better specify the task and url."


if __name__ == "__main__":
    # mcp.run(transport="sse")
    mcp.run(transport="stdio")
