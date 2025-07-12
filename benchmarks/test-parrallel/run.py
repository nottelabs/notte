import json
from pathlib import Path
from typing import Any, cast

from bench_types import (  # pyright: ignore[reportImplicitRelativeImport]
    BenchmarkTask,
    LLMCall,
    RunOutput,
    Step,
    TaskResult,
)
from loguru import logger
from notte_agent.agent import NotteAgent
from notte_browser.session import NotteSession
from notte_core.utils.webp_replay import ScreenshotReplay
from notte_eval.evaluators.evaluator import EvaluationResponse, Evaluator
from patcher import AgentPatcher  # pyright: ignore[reportImplicitRelativeImport]

import notte


def read_tasks(path: Path | str) -> list[BenchmarkTask]:
    tasks: list[BenchmarkTask] = []

    with open(path, "r") as f:
        for line in f.readlines():
            tasks.append(BenchmarkTask.model_validate_json(line))

    return tasks


def run_task(session: NotteSession, task: BenchmarkTask) -> bool:
    agent = notte.Agent(session=session, reasoning_model="gemini/gemini-2.5-flash", max_steps=5)
    resp = agent.run(url=task.url, task=task.question)
    return resp.success


def trim_image_messages(input_content: list[dict[Any, Any]]) -> None:
    # trim down: remove images in the message history
    for msg in input_content:
        if "content" in msg and isinstance(msg["content"], list):
            for submsg in msg["content"]:  # type: ignore
                if "type" in submsg and submsg["type"] == "image_url" and "image_url" in submsg:
                    submsg["image_url"] = "benchmark: removed"


async def run_task_with_session(task: BenchmarkTask, headless: bool, model: str) -> RunOutput:
    logger.info(task)
    logger.info("Starting task ...")
    async with notte.Session(headless=headless) as session:
        agent = notte.Agent(session=session, reasoning_model=model).create_agent()
        agent = cast(NotteAgent, agent)
        patcher = AgentPatcher()
        _ = patcher.log(agent.llm, ["completion"])
        _ = patcher.log(agent, ["step", "run"])

        output = await agent.run(task=f"Your task: {task.question}", url=task.url)
        logger.info(f"Agent success: {output.success}")

    output.llm_messages = json.loads(json.dumps(output.llm_messages, default=str))
    for lusage in output.llm_usage:
        lusage.messages = json.loads(json.dumps(lusage.messages, default=str))

    # WIP/known issue: no steps in per step calls -> no screenshots generated
    psc = patcher.find_encompassed_events("FalcoAgent.step")

    return RunOutput(
        logged_data=patcher.logged_data,
        per_step_calls=psc,
        output=output,
    )


async def process_output(task: BenchmarkTask, out: RunOutput) -> TaskResult:
    steps: list[Step] = []
    screenshots: list[bytes] = []
    for (step, in_step_calls), hist in zip(out.per_step_calls, out.output.trajectory):
        last_url = ""
        if hist.result.success:
            obs = hist.obs
            screen = obs.screenshot
            screenshots.append(screen.bytes())

            last_url = obs.metadata.url

        llm_calls: list[LLMCall] = []
        llm_calls_logs = in_step_calls["LLMEngine.completion"]
        for llm_call_log in llm_calls_logs:
            input_content = json.loads(llm_call_log.input_data)
            input_content = input_content["messages"]

            trim_image_messages(input_content)

            output_content = json.loads(llm_call_log.output_data)
            response = output_content["choices"][0]["message"]
            tokens = output_content["usage"]

            llm_calls.append(
                LLMCall(
                    input_tokens=tokens["prompt_tokens"],
                    output_tokens=tokens["completion_tokens"],
                    messages_in=input_content,
                    message_out=response,
                )
            )

        # for llm_call in llm_calls:
        step = Step(url=last_url, duration_in_s=step.duration_in_s, llm_calls=llm_calls)
        steps.append(step)

    if "NotteAgent.run" not in out.logged_data:
        raise ValueError(
            f"NotteAgent.run not found in logged data. Valid keys are: {', '.join(out.logged_data.keys())}"
        )

    # if len(screenshots) == 0:
    #     raise ValueError("no screenshots")

    if len(steps) == 0:
        raise ValueError(f"no steps, {len(screenshots)} screenshots")

    return TaskResult(
        success=out.output.success,
        duration_in_s=out.logged_data["NotteAgent.run"][0].duration_in_s,
        agent_answer=str(out.output.answer),
        task=task,
        steps=steps,
        screenshots=ScreenshotReplay.from_bytes(screenshots),
    )


async def evaluate(evaluator: Evaluator, result: TaskResult) -> EvaluationResponse:
    return await evaluator.eval(result.agent_answer, result.task.question, result.screenshots.b64_screenshots)
