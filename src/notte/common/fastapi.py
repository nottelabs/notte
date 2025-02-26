from typing import Annotated

from fastapi import APIRouter, HTTPException

from notte.common.agent.base import BaseAgent
from notte.common.agent.types import AgentRequest, AgentResponse


def create_agent_router(agent: BaseAgent, prefix: str = "agent") -> APIRouter:
    """
    Creates a FastAPI router that serves the given agent.

    Args:
        agent: The BaseAgent implementation to serve
        prefix: Optional URL prefix for the API endpoints

    Returns:
        APIRouter instance with agent endpoints
    """
    router = APIRouter(
        prefix=prefix,
        tags=[agent.__class__.__name__],
    )

    @router.post("/run", response_model=AgentResponse)
    async def run_agent(request: Annotated[AgentRequest, "Agent request parameters"]) -> AgentResponse:  # type: ignore[unused-function]
        try:
            return await agent.run(task=request.task, url=request.url)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return router
