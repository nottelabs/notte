from notte_browser.session import NotteSession
from pydantic import BaseModel

import notte


class BenchmarkTask(BaseModel):
    task: str
    url: str | None = None


def run_task(session: NotteSession, task: BenchmarkTask) -> bool:
    agent = notte.Agent(session=session, reasoning_model="gemini/gemini-2.0-flash", max_steps=5)
    resp = agent.run(url=task.url, task=task.task)
    return resp.success
