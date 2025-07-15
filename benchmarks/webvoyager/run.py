import base64
import json
import time
from pathlib import Path
from typing import cast

from bench_types import (  # pyright: ignore[reportImplicitRelativeImport]
    BenchmarkTask,
    RunOutput,
    TaskResult,
)
from evaluator import EvaluationResponse, Evaluator  # pyright: ignore[reportImplicitRelativeImport]
from loguru import logger
from notte_agent.agent import NotteAgent
from notte_browser.session import NotteSession
from notte_core.utils.webp_replay import ScreenshotReplay

import notte


def read_tasks(path: Path | str, n_runs: int = 1) -> list[tuple[BenchmarkTask, int]]:
    tasks: list[tuple[BenchmarkTask, int]] = []

    with open(path, "r") as f:
        for line in f.readlines():
            for run_num in range(n_runs):
                tasks.append((BenchmarkTask.model_validate_json(line), run_num))

    return tasks


def run_task(session: NotteSession, task: BenchmarkTask) -> bool:
    agent = notte.Agent(session=session, reasoning_model="gemini/gemini-2.5-flash", max_steps=5)
    resp = agent.run(url=task.url, task=task.question)
    return resp.success


async def run_task_with_session(task: BenchmarkTask, headless: bool, model: str) -> RunOutput:
    logger.info(task)
    logger.info("Starting task ...")
    async with notte.Session(headless=headless) as session:
        agent = notte.Agent(session=session, reasoning_model=model).create_agent()
        agent = cast(NotteAgent, agent)

        start_time = time.time()
        output = await agent.run(task=f"Your task: {task.question}", url=task.url)
        logger.info(f"Agent success: {output.success}")
        end_time = time.time()

    output.llm_messages = json.loads(json.dumps(output.llm_messages, default=str))
    for lusage in output.llm_usage:
        lusage.messages = json.loads(json.dumps(lusage.messages, default=str))

    return RunOutput(
        duration_in_s=end_time - start_time,
        output=output,
    )


async def process_output(task: BenchmarkTask, out: RunOutput) -> TaskResult:
    screenshots: list[bytes] = []
    for hist in out.output.trajectory:
        obs = hist.obs
        screen = obs.screenshot
        screenshots.append(screen.bytes())

    input_tokens = sum(u.usage.get("prompt_tokens", 0) for u in out.output.llm_usage)
    output_tokens = sum(u.usage.get("completion_tokens", 0) for u in out.output.llm_usage)

    return TaskResult(
        success=out.output.success,
        duration_in_s=out.duration_in_s,
        agent_answer=str(out.output.answer),
        task=task,
        total_input_tokens=input_tokens,
        total_output_tokens=output_tokens,
        steps=out.output.trajectory,
        screenshots=ScreenshotReplay.from_bytes(screenshots),
    )


async def evaluate(evaluator: Evaluator, result: TaskResult) -> EvaluationResponse:
    b64_screenshots: list[str] = result.screenshots.b64_screenshots
    screenshots: list[bytes] = [base64.b64decode(screen) for screen in b64_screenshots]

    expected_answer = result.task.answer

    if expected_answer is None:
        expected_answer = "No expected result provided."

    return await evaluator.eval(result.agent_answer, result.task.question, expected_answer, screenshots)
