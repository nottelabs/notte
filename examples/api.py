from fastapi import FastAPI
from notte.common.fastapi import create_agent_router
from notte_agents.falco.agent import FalcoAgent as Agent, FalcoAgentConfig as AgentConfig

config = AgentConfig()
_ = config.cerebras().dev_mode()
_ = config.env.disable_web_security().not_headless().cerebras().steps(10)

agent = Agent(config=config)

app = FastAPI()


@app.get("/")
def health_check():
    return {"status": "ok"}


router = create_agent_router(agent, prefix="/agent")
app.include_router(router)


# uvicorn examples.api:app --reload
# export task="Go to twitter.com and login with the account lucasgiordano@gmail.com and password mypassword8982"
# curl -X POST "http://localhost:8000/agent/run" -H "Content-Type: application/json" -d '{"task": "$task"}'
