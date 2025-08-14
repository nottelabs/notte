import base64
import io
import json
import time
from pathlib import Path
from typing import cast

import notte
from loguru import logger
from notte_agent.agent import NotteAgent
from notte_browser.session import NotteSession
from notte_core.trajectory import StepBundle
from notte_core.utils.webp_replay import ScreenshotReplay
from notte_sdk import NotteClient

from notte_eval.evaluators.evaluator import EvaluationResponse, Evaluator
from notte_eval.webvoyager.bench_types import (
    BenchmarkTask,
    RunOutput,
    SdkRunOutput,
    SdkTaskResult,
    TaskResult,
)


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


async def run_task_with_session(
    task: BenchmarkTask, headless: bool, model: str, use_vision: bool, max_steps: int, user_agent: str | None
) -> RunOutput:
    logger.info(task)
    logger.info("Starting task ...")
    async with notte.Session(headless=headless, user_agent=user_agent) as session:
        agent = notte.Agent(
            session=session, reasoning_model=model, use_vision=use_vision, max_steps=max_steps
        ).create_agent()
        agent = cast(NotteAgent, agent)

        start_time = time.time()
        output = await agent.arun(task=f"Your task: {task.question}", url=task.url)
        logger.info(f"Agent success: {output.success}")
        end_time = time.time()

    output.llm_messages = json.loads(json.dumps(output.llm_messages, default=str))
    if output.llm_usage is not None:
        for lusage in output.llm_usage.steps:
            lusage.messages = json.loads(json.dumps(lusage.messages, default=str))

    return RunOutput(
        duration_in_s=end_time - start_time,
        output=output,
    )


async def run_task_with_sdk(
    task: BenchmarkTask,
    client: NotteClient,
    headless: bool,
    model: str,
    use_vision: bool,
    max_steps: int,
    proxies: bool,
    user_agent: str | None,
) -> SdkRunOutput:
    logger.info(task)
    logger.info("Starting task ...")
    with client.Session(headless=headless, proxies=proxies, user_agent=user_agent) as session:
        agent = client.Agent(session=session, reasoning_model=model, use_vision=use_vision, max_steps=max_steps)

        start_time = time.time()
        output = agent.run(task=f"Your task: {task.question}", url=task.url)
        logger.info(f"Agent success: {output.success}")
        end_time = time.time()

        replay = agent.replay()

        screenshots: list[bytes] = []

        for i in range(len(output.steps)):
            frame = replay.frame(i)

            frame_buffer = io.BytesIO()
            frame.save(frame_buffer, format="PNG")
            frame_bytes = frame_buffer.getvalue()

            screenshots.append(frame_bytes)

    return SdkRunOutput(
        duration_in_s=end_time - start_time,
        output=output,
        replay=ScreenshotReplay.from_bytes(screenshots),
    )


async def process_output(task: BenchmarkTask, out: RunOutput) -> TaskResult:
    screenshots: list[bytes] = []
    for hist in out.output.trajectory.step_iterator():
        obs = hist.observation
        if obs is not None:
            screen = obs.screenshot
            screenshots.append(screen.bytes())

    input_tokens = 0
    output_tokens = 0
    if out.output.llm_usage is not None:
        input_tokens = out.output.llm_usage.aggregated_usage.prompt_tokens
        output_tokens = out.output.llm_usage.aggregated_usage.completion_tokens

    return TaskResult(
        success=out.output.success,
        duration_in_s=out.duration_in_s,
        agent_answer=str(out.output.answer),
        task=task,
        total_input_tokens=input_tokens,
        total_output_tokens=output_tokens,
        steps=[step for step in out.output.trajectory.step_iterator()],
        screenshots=ScreenshotReplay.from_bytes(screenshots),
    )


async def process_output_sdk(task: BenchmarkTask, out: SdkRunOutput) -> SdkTaskResult:
    input_tokens = -1
    output_tokens = -1

    return SdkTaskResult(
        success=out.output.success if out.output.success is not None else False,
        duration_in_s=out.duration_in_s,
        agent_answer=str(out.output.answer),
        task=task,
        total_input_tokens=input_tokens,
        total_output_tokens=output_tokens,
        steps=[StepBundle(agent_completion=step) for step in out.output.steps],
        screenshots=out.replay,
    )


async def evaluate(evaluator: Evaluator, result: TaskResult | SdkTaskResult) -> EvaluationResponse:
    b64_screenshots: list[str] = result.screenshots.b64_screenshots
    screenshots: list[bytes] = [base64.b64decode(screen) for screen in b64_screenshots]

    expected_answer = result.task.answer

    if expected_answer is None:
        expected_answer = "No expected result provided."

    return await evaluator.eval(result.agent_answer, result.task.question, expected_answer, screenshots)
