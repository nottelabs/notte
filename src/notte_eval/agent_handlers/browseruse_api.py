import asyncio
import os
from datetime import datetime
from typing import Any

import requests
from pydantic import BaseModel
from typing_extensions import override

from notte_eval.screenshots import Screenshots
from notte_eval.task_types import AgentBenchmark, TaskResult
from notte_eval.webvoyager.load_data import WebVoyagerTask


class BrowserUseStep(BaseModel):
    id: str
    step: int
    evaluation_previous_goal: str
    next_goal: str


class BrowserUseBrowserData(BaseModel):
    cookies: list[dict[Any, Any]] = []


class BrowserUseTaskResponse(BaseModel):
    id: str
    task: str
    live_url: str
    output: str
    status: str
    created_at: datetime
    finished_at: datetime
    steps: BrowserUseStep
    browser_data: BrowserUseBrowserData | None = None


class BrowserUseAPIInput(BaseModel):
    url: str = "https://api.browser-use.com/api/v1/run-task"
    max_steps: int
    max_time: float = 100
    sleep_time: float = 10


class BrowserUseAPIOutput(BaseModel):
    answer: str


class BrowserUseAPIBench(AgentBenchmark[BrowserUseAPIInput, BrowserUseAPIOutput]):
    def __init__(self, params: BrowserUseAPIInput):
        super().__init__(params)

    @override
    async def run_agent(self, task: WebVoyagerTask) -> BrowserUseAPIOutput:
        token = os.getenv("BROWSERUSE_API_KEY")

        session = requests.Session()

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        prompt = f"""You are a helpful web agent.
        Now you are given the task: {task.question}.
        Please interact with : {task.url or "the web"} to get the answer.
        """

        payload = {"task": prompt, "save_browser_data": False}

        import logging

        logging.warning(f"{payload=} {headers=}")
        task_creation_url = "https://api.browser-use.com/api/v1/run-task"

        response = session.request("POST", url=task_creation_url, json=payload, headers=headers)
        response.raise_for_status()

        task_id = response.json()["id"]
        task_status_url = f"https://api.browser-use.com/api/v1/task/{task_id}"

        sleep_time = 0

        while sleep_time < self.params.max_time:
            response = session.get(task_status_url, headers=headers)
            response.raise_for_status()

            resp_model = BrowserUseTaskResponse.model_validate(response.json())

            if resp_model.status in ["finished", "stopped", "paused", "failed"]:
                return BrowserUseAPIOutput(answer=resp_model.status)

            sleep_time += self.params.sleep_time
            await asyncio.sleep(self.params.sleep_time)

        return BrowserUseAPIOutput(answer="overtime")

    @override
    async def process_output(self, task: WebVoyagerTask, out: BrowserUseAPIOutput) -> TaskResult:
        return TaskResult(
            success=False,
            duration_in_s=0,
            agent_answer="",
            task=task,
            steps=[],
            screenshots=Screenshots.from_base64([]),
        )
