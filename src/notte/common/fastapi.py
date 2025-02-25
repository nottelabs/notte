from __future__ import annotations

from typing import Annotated

from notte.common.agent.base import BaseAgent
from notte.common.agent.types import AgentResponse
from notte.sdk.types import AgentRequest


def create_agent_router(agent: BaseAgent, prefix: str = "agent") -> APIRouter:  # type: ignore[reportUnknownParameterType]
    """
    Creates a FastAPI router that serves the given agent.

    Args:
        agent: The BaseAgent implementation to serve
        prefix: Optional URL prefix for the API endpoints

    Returns:
        APIRouter instance with agent endpoints
    """
    router = APIRouter(  # type: ignore[reportUnknownMemberType]
        prefix=prefix,
        tags=[agent.__class__.__name__],
    )

    @router.post("/run", response_model=AgentResponse)
    async def run_agent(request: Annotated[AgentRequest, "Agent request parameters"]) -> AgentResponse:
        try:
            return await agent.run(task=request.task, url=request.url)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return router  # type: ignore[reportUnknownReturn]
