import asyncio
import json
import logging
import os
import time
import traceback
import typing
from typing import Any

import pandas as pd
import pytest
import tiktoken
from joblib import Parallel, delayed
from pydantic import BaseModel, computed_field

from eval.patcher import AgentPatcher
from eval.webvoyager.load_data import (
    WebVoyagerSubset,
    WebVoyagerTask,
    load_webvoyager_data,
)
from examples.simple.agent import HistoryType, SimpleAgent
from notte.browser.pool import BrowserPool
from notte.common.trajectory_history import TrajectoryStep


class ModelOutput(BaseModel):
    answer: str
    success: bool
    trajectory: list[TrajectoryStep]
    num_steps: int


class RunOutput(BaseModel):
    success: bool
    answer: str
    trajectory: list[TrajectoryStep]
    num_steps: int
    input_tokens: dict[str, list[Any]]
    output_tokens: dict[str, list[Any]]
    duration_in_s: float


class LLMCall(BaseModel):
    input_tokens: int
    output_tokens: int
    messages_in: list[dict[str, Any]]
    message_out: dict[str, Any]


class TaskResult(BaseModel):
    success: bool = False
    duration_in_s: float
    agent_answer: str
    task: WebVoyagerTask
    num_steps: int
    llm_calls: list[LLMCall]
    replay_steps: str

    @computed_field
    def task_description(self) -> str:
        return self.task.question

    @computed_field
    def task_id(self) -> int:
        return self.task.id

    @computed_field
    def task_website(self) -> str:
        return self.task.name

    @computed_field
    def reference_answer(self) -> str:
        return self.task.ref_answers[0].answer

    @computed_field
    def total_input_tokens(self) -> int:
        return sum(step.input_tokens for step in self.llm_calls)

    @computed_field
    def total_output_tokens(self) -> int:
        return sum(step.output_tokens for step in self.llm_calls)

    @computed_field
    def last_message(self) -> str:
        if len(self.llm_calls) == 0:
            return ""

        return json.dumps(self.llm_calls[-1].message_out)


@pytest.fixture(scope="session")
def agent_llm(pytestconfig):
    return pytestconfig.getoption("agent_llm")


@pytest.fixture(scope="session")
def n_jobs(pytestconfig):
    return pytestconfig.getoption("n_jobs")


@pytest.fixture(scope="session")
def include_screenshots(pytestconfig):
    return pytestconfig.getoption("include_screenshots").lower() == "true"


@pytest.fixture(scope="session")
def history_type(pytestconfig):
    return pytestconfig.getoption("history_type")


def run_agent(
    browser_pool: BrowserPool, agent_llm: str, task: WebVoyagerTask, include_screenshots: bool, history_type: str
) -> tuple[WebVoyagerTask, RunOutput]:
    task_str = f"Your task: {task.question}. Use {task.url or 'the web'} to answer the question."
    start = time.time()
    patcher = AgentPatcher()
    agent = SimpleAgent(
        pool=browser_pool,
        model=agent_llm,
        headless=True,
        raise_on_failure=False,
        include_screenshot=include_screenshots,
        history_type=HistoryType(history_type),
    )

    async def _async_run() -> tuple[ModelOutput, AgentPatcher]:
        try:

            _ = patcher.log_io(agent.llm, ["completion"])

            output = await agent.run(task_str)
            model_output = ModelOutput(
                answer=output.answer,
                success=output.success,
                trajectory=agent.trajectory.steps,
                num_steps=len(output.trajectory),
            )

            return model_output, patcher

        except Exception as e:
            logging.error(f"Error running task: {task}: {e} {traceback.format_exc()}")

        model_output = ModelOutput(
            answer="",
            success=False,
            trajectory=agent.trajectory.steps,
            num_steps=len(patcher.input_data["LLMEngine.completion"]),
        )

        return model_output, patcher

    output, patcher = asyncio.run(_async_run())

    return task, RunOutput(
        success=output.success,
        answer=output.answer,
        trajectory=output.trajectory,
        num_steps=output.num_steps,
        duration_in_s=time.time() - start,
        input_tokens=patcher.input_data,
        output_tokens=patcher.output_data,
    )


@pytest.mark.timeout(60 * 60)  # fail after 1 hour
@pytest.mark.asyncio
async def test_benchmark_webvoyager(
    agent_llm: str, n_jobs: int, include_screenshots: bool, history_type: str, monkeypatch
) -> None:
    tasks = load_webvoyager_data(WebVoyagerSubset.Simple)

    SUFFIX = "_CICD"
    for api_key_str in ["CEREBRAS_API_KEY", "OPENAI_API_KEY"]:

        api_key = os.environ.get(f"{api_key_str}{SUFFIX}")

        if api_key is None:
            logging.warning(f"CICD key for {api_key_str} not found, using default API key")
            api_key = os.environ.get(api_key_str)

        monkeypatch.setenv(api_key_str, api_key)

    browser_pool = BrowserPool()

    # find a better way to handle single job / asyncio joblib
    if n_jobs == 1:
        results = [run_agent(browser_pool, agent_llm, task, include_screenshots, history_type) for task in tasks]
    else:
        results: list[tuple[WebVoyagerTask, RunOutput]] = typing.cast(
            list[tuple[WebVoyagerTask, RunOutput]],
            Parallel(n_jobs=n_jobs)(
                delayed(run_agent)(browser_pool, agent_llm, task, include_screenshots, history_type) for task in tasks
            ),
        )

    parsed_results = [parse_output(agent_llm, task, include_screenshots, run_output) for task, run_output in results]

    df = pd.DataFrame((x.model_dump() for x in parsed_results)).sort_values(by=["task_website", "task_id"])

    MD_COLUMNS = [
        "task_website",
        "task_id",
        "success",
        "duration_in_s",
        "num_steps",
        "total_input_tokens",
        "total_output_tokens",
    ]
    HTML_COLUMNS = MD_COLUMNS + ["replay_steps"]

    filtered = df[HTML_COLUMNS].copy()
    filtered.loc["Average"] = filtered.mean(numeric_only=True)
    filtered = filtered.fillna("")

    logging.info(f"\n\n{filtered[MD_COLUMNS].to_markdown()}")

    os.makedirs("dist", exist_ok=True)

    def format_html_code(code: str) -> str:
        """Styler function to format code blocks in Pandas to_html()."""
        return (
            "<details>\n"
            "    <summary>Click to expand</summary>\n"
            '    <pre style="white-space: pre-wrap;"><code class="language-python">\n'
            f"{code}\n"
            "    </code></pre>\n"
            "</details>"
        )

    filtered.to_html(
        os.path.join("dist", "results.html"),
        formatters={"replay_steps": format_html_code},
        escape=False,
        render_links=True,
    )
    df.to_json(os.path.join("dist", "results.jsonl"), orient="records", lines=True)

    assert df.success.all()


def parse_output(agent_key: str, task: WebVoyagerTask, include_screenshots: bool, run_output: RunOutput) -> TaskResult:
    encoding = tiktoken.get_encoding("cl100k_base")

    def get_content(message: dict[str, Any]) -> str:
        message = message["content"][0]
        if isinstance(message, str):
            return message
        return message["text"]

    input_messages = [json.loads(message) for message in run_output.input_tokens["LLMEngine.completion"]]
    input_tokens = [" ".join(get_content(message) for message in step["messages"]) for step in input_messages]
    num_inputs_per_step = [len(encoding.encode(tokens)) for tokens in input_tokens]

    output_messages = [json.loads(message) for message in run_output.output_tokens["LLMEngine.completion"]]
    output_tokens = [step["choices"][0]["message"]["content"] for step in output_messages]
    num_outputs_per_step = [len(encoding.encode(tokens)) for tokens in output_tokens]

    try:
        agent_answer = run_output.answer
    except Exception:
        agent_answer = ""

    llm_calls = []
    for inp_message, out_message, inp_tokens, out_tokens in zip(
        input_messages, output_messages, num_inputs_per_step, num_outputs_per_step
    ):

        messages_in = [message for message in inp_message["messages"]]
        message_out = out_message["choices"][0]["message"]

        llm_calls.append(
            LLMCall(
                input_tokens=inp_tokens,
                output_tokens=out_tokens,
                messages_in=messages_in,
                message_out=message_out,
            )
        )

    task_res = TaskResult(
        success=run_output.success,
        duration_in_s=run_output.duration_in_s,
        num_steps=run_output.num_steps,
        agent_answer=agent_answer,
        task=task,
        llm_calls=llm_calls,
        replay_steps=format_code(run_output),
    )

    return task_res


def format_code(run_output: RunOutput) -> str:
    LINE_TAG = "obs = env.raw_step({action_name})"
    steps = []
    for step in run_output.trajectory:
        for result in step.results:
            action = result.input
            action_name = f"{action.__class__.__name__}.model_validate({action.model_dump_json()})"
            steps.append(LINE_TAG.format(action_name=action_name))

    replay_steps = "\n".join(steps)
    return replay_steps
