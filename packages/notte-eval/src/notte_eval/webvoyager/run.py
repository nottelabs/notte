from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import cast

import loguru
import notte
from notte_agent.agent import NotteAgent
from notte_browser.session import NotteSession
from notte_core.agent_types import AgentCompletion
from notte_core.common.config import BrowserType
from notte_core.common.logging import logger
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


class LoggingSink:
    def __init__(self):
        self.messages: list[str] = []

    def write(self, message: str):
        message = message.strip()
        if message:
            self.messages.append(message)

    def __call__(self, message: loguru.Message):
        """Handle loguru's callable sink interface"""
        # Format the message with timestamp and level info
        formatted_message = f"{message.record['time'].strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} | {message.record['level'].name:<8} | {message.record['name']}:{message.record['function']}:{message.record['line']} - {message.record['message']}"
        self.messages.append(formatted_message)


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
    task: BenchmarkTask,
    headless: bool,
    model: str,
    use_vision: bool,
    max_steps: int,
    user_agent: str | None,
    browser_type: BrowserType,
) -> RunOutput:
    # Set up loguru logging capture
    sink = LoggingSink()

    # Remove existing handlers and add our sink
    logger.remove()
    _ = logger.add(
        sink,
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    )

    def get_logs() -> dict[str, str]:
        logs: dict[str, str] = {}
        logs["loguru"] = "\n".join(sink.messages)
        return logs

    logger.info(task)
    logger.info("Starting task ...")

    try:
        async with notte.Session(headless=headless, user_agent=user_agent, browser_type=browser_type) as session:
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
            logs=get_logs(),
        )
    finally:
        # Restore default loguru configuration
        logger.remove()
        _ = logger.add(sys.stderr, level="INFO")


def mp4_bytes_to_frame_bytes(mp4_bytes: bytes) -> list[bytes]:
    """
    Convert MP4 video bytes to a list of frame bytes using ffmpeg.

    Args:
        mp4_bytes: The MP4 video as bytes

    Returns:
        List of bytes, where each item is a PNG image of a frame
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write input MP4 to temp file
        input_path = os.path.join(tmpdir, "input.mp4")
        with open(input_path, "wb") as f:
            _ = f.write(mp4_bytes)

        # Output pattern for frames
        output_pattern = os.path.join(tmpdir, "frame_%04d.png")

        # Run ffmpeg to extract frames
        _ = subprocess.run(
            ["ffmpeg", "-i", input_path, "-f", "image2", output_pattern], check=True, capture_output=True
        )

        # Read all frame files into bytes
        frame_bytes_list: list[bytes] = []
        frame_files = sorted(Path(tmpdir).glob("frame_*.png"))

        for frame_file in frame_files:
            with open(frame_file, "rb") as f:
                frame_bytes_list.append(f.read())

        return frame_bytes_list


async def run_task_with_sdk(
    task: BenchmarkTask,
    client: NotteClient,
    model: str,
    use_vision: bool,
    max_steps: int,
    proxies: bool,
    browser_type: BrowserType,
    user_agent: str | None,
) -> SdkRunOutput:
    # Set up loguru logging capture
    sink = LoggingSink()

    # Remove existing handlers and add our sink
    logger.remove()
    _ = logger.add(
        sink,
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    )

    def get_logs() -> dict[str, str]:
        logs: dict[str, str] = {}
        logs["loguru"] = "\n".join(sink.messages)
        return logs

    logger.info(task)
    logger.info("Starting task ...")

    try:
        with client.Session(proxies=proxies, user_agent=user_agent, browser_type=browser_type) as session:
            agent = client.Agent(session=session, reasoning_model=model, use_vision=use_vision, max_steps=max_steps)

            session_id = session.session_id
            start_time = time.time()
            output = agent.run(task=f"Your task: {task.question}", url=task.url)
            logger.info(f"Agent success: {output.success}")
            end_time = time.time()

            video_replay = b""
            try:
                replay = agent.replay()
                video_replay = replay.replay
                screenshots = mp4_bytes_to_frame_bytes(replay.replay)
            except Exception as e:
                logger.opt(exception=True).error(str(e))
                screenshots = []

        return SdkRunOutput(
            session_id=session_id,
            duration_in_s=end_time - start_time,
            output=output,
            video_replay=video_replay,
            replay=ScreenshotReplay.from_bytes(screenshots),
            logs=get_logs(),
        )
    finally:
        # Restore default loguru configuration
        logger.remove()
        _ = logger.add(sys.stderr, level="INFO")


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
        logs=out.logs,
    )


async def process_output_sdk(task: BenchmarkTask, out: SdkRunOutput) -> SdkTaskResult:
    input_tokens = -1
    output_tokens = -1

    return SdkTaskResult(
        success=out.output.success if out.output.success is not None else False,
        duration_in_s=out.duration_in_s,
        session_id=out.session_id,
        agent_answer=str(out.output.answer),
        video_replay=out.video_replay,
        task=task,
        total_input_tokens=input_tokens,
        total_output_tokens=output_tokens,
        steps=[
            StepBundle(agent_completion=AgentCompletion.model_validate(step["value"]))
            for step in out.output.steps
            if step.get("type") == "agent_completion"
        ],
        screenshots=out.replay,
        logs=out.logs,
    )


async def evaluate(evaluator: Evaluator, result: TaskResult | SdkTaskResult) -> EvaluationResponse:
    b64_screenshots: list[str] = result.screenshots.b64_screenshots
    screenshots: list[bytes] = [base64.b64decode(screen) for screen in b64_screenshots]

    expected_answer = result.task.answer

    if expected_answer is None:
        expected_answer = "No expected result provided."

    return await evaluator.eval(result.agent_answer, result.task.question, expected_answer, screenshots)
