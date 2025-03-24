from __future__ import annotations

from typing import Annotated

try:
    from fastapi import APIRouter, HTTPException  # type: ignore[reportMissingModuleSource]
except ImportError:
    raise ImportError("fastapi is required to use the FastAPI router. Install it with 'uv sync --extra api'")

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

    @router.post("/run", response_model=AgentResponse)  # type: ignore[reportUntypedFunctionDecorator]
    async def run_agent(request: Annotated[AgentRequest, "Agent request parameters"]) -> AgentResponse:  # type: ignore[reportUnusedFunction]
        try:
            return await agent.run(task=request.task, url=request.url)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return router  # type: ignore[reportUnknownReturn]
