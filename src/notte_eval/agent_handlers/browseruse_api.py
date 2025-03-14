import asyncio
import json
import logging
import os
import time
from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel
from typing_extensions import override

from notte.utils.webp_replay import ScreenshotReplay
from notte_eval.data.load_data import BenchmarkTask
from notte_eval.task_types import AgentBenchmark, Step, TaskResult


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
    output: str | None
    status: str
    created_at: datetime
    finished_at: datetime | None
    steps: list[BrowserUseStep]
    browser_data: BrowserUseBrowserData | None = None


class BrowserUseTaskMedia(BaseModel):
    recordings: list[str] | None


class BrowserUseAPIInput(BaseModel):
    url: str = "https://api.browser-use.com/api/v1/run-task"
    max_steps: int
    max_time: float = 100
    sleep_time: float = 10


class BrowserUseAPIOutput(BaseModel):
    duration_in_s: float
    output: BrowserUseTaskResponse | None = None
    media: BrowserUseTaskMedia | None = None


class BrowserUseAPIBench(AgentBenchmark[BrowserUseAPIInput, BrowserUseAPIOutput]):
    def __init__(self, params: BrowserUseAPIInput):
        super().__init__(params)

    @override
    async def run_agent(self, task: BenchmarkTask) -> BrowserUseAPIOutput:
        start_time = time.time()

        token = os.getenv("BROWSERUSE_API_KEY")

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(headers=headers) as session:
            prompt = f"""You are a helpful web agent.
            Now you are given the task: {task.question}.
            Please interact with : {task.url or "the web"} to get the answer.
            """

            payload = {"task": prompt, "save_browser_data": False}

            task_creation_url = "https://api.browser-use.com/api/v1/run-task"
            task_stop_url = "https://api.browser-use.com/api/v1/stop-task"

            run_resp = await session.request("POST", url=task_creation_url, json=payload)
            _ = run_resp.raise_for_status()

            task_id: str = run_resp.json()["id"]
            task_status_url = f"https://api.browser-use.com/api/v1/task/{task_id}"

            sleep_time = 0
            while True:
                task_response = await session.get(task_status_url)

                logging.info(f"{json.dumps(task_response.json(), indent=2)}\n")
                _ = task_response.raise_for_status()

                resp_model = BrowserUseTaskResponse.model_validate(task_response.json())

                should_return = False
                if len(resp_model.steps) >= self.params.max_steps:
                    should_return = True

                if sleep_time > self.params.max_time:
                    should_return = True

                if resp_model.status in ["finished", "stopped", "paused", "failed"]:
                    should_return = True

                if should_return:
                    # get media (empty for now?)
                    media_url = f"https://api.browser-use.com/api/v1/task/{task_id}/media"
                    media_resp = await session.get(media_url)
                    _ = media_resp.raise_for_status()

                    # enforce stop because it doesnt seem to stop by default
                    stop_resp = await session.put(task_stop_url, params={"task_id": task_id})
                    _ = stop_resp.raise_for_status()

                    media = BrowserUseTaskMedia.model_validate(media_resp.json())

                    logging.info(f"{media.model_dump_json(indent=2)}\n")
                    return BrowserUseAPIOutput(output=resp_model, media=media, duration_in_s=time.time() - start_time)

                sleep_time += self.params.sleep_time
                await asyncio.sleep(self.params.sleep_time)

    @override
    async def process_output(self, task: BenchmarkTask, out: BrowserUseAPIOutput) -> TaskResult:
        output = out.output
        if output is None:
            return TaskResult(
                success=False,
                duration_in_s=0,
                agent_answer="",
                task=task,
                steps=[],
                screenshots=ScreenshotReplay.from_base64([]),
            )

        steps: list[Step] = []
        for step in output.steps:
            steps.append(Step(url=step.next_goal, duration_in_s=0, llm_calls=[]))

        return TaskResult(
            success=True,
            duration_in_s=out.duration_in_s,
            agent_answer=output.output or "No output",
            task=task,
            steps=steps,
            screenshots=ScreenshotReplay.from_base64([]),
        )
