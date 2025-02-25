import os
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI  # type: ignore[reportMissingModuleSource]
from loguru import logger

_ = load_dotenv()

from notte.common.fastapi import create_agent_router  # noqa # type: ignore[reportUnknownMemberType]

# load the agent you are interested in
from notte.agents.falco.agent import FalcoAgent as Agent  # noqa
from notte.agents.falco.agent import FalcoAgentConfig as AgentConfig  # noqa

headless = os.getenv("HEADLESS", "false")

config = AgentConfig().cerebras().map_env(lambda env: (env.disable_web_security().cerebras().user_mode()))

if headless == "true":
    logger.info("Running in headless mode")
    _ = config.env.headless()

agent = Agent(config=config)

app: Any = FastAPI()


@app.get("/")
def health_check():
    return {"status": "ok"}


router = create_agent_router(agent, prefix="/agent")  # type: ignore[reportUnknownVariableType]
app.include_router(router)


# uv sync --extra api
# uv run python -m uvicorn examples.fastapi_agent:app --host 0.0.0.0 --port 8000
# export task="Go to twitter.com and login with the account $email and password $password"
# curl -X POST "http://localhost:8000/agent/run" -H "Content-Type: application/json" -d '{"task": "$task"}'
