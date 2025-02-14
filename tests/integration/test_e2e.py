import asyncio
import concurrent.futures
import contextlib
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import cloudpickle
import pandas as pd
import pytest
import tiktoken
from loguru import logger as loguru_logger
from pydantic import BaseModel, computed_field

from eval.patcher import AgentPatcher
from eval.webvoyager.load_data import (
    WebVoyagerSubset,
    WebVoyagerTask,
    load_webvoyager_data,
)
from examples.simple.agent import HistoryType, RaiseCondition, SimpleAgent
from notte.browser.pool import BrowserPool
from notte.common.trajectory_history import TrajectoryStep

DISPLAY_MD_COLUMNS = [
    "task_website",
    "task_id",
    "success",
    "duration_in_s",
    "num_steps",
    "total_input_tokens",
    "total_output_tokens",
]
DISPLAY_HTML_COLUMNS = DISPLAY_MD_COLUMNS + ["replay_steps"]


class RunParameters(BaseModel):
    agent_llm: str
    n_jobs: int
    include_screenshots: bool
    history_type: str
    tries_per_task: int


@dataclass(frozen=True)
class RunKey:
    task_name: str
    task_id: int
    run_id: int


class RunOutput(BaseModel):
    success: bool
    answer: str
    trajectory: list[TrajectoryStep]
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


async def run_agent(browser_pool: BrowserPool, task: WebVoyagerTask, run_parameters: RunParameters) -> bytes:
    task_str = f"Your task: {task.question}. Use {task.url or 'the web'} to answer the question."
    start = time.time()
    patcher = AgentPatcher()
    agent = SimpleAgent(
        pool=browser_pool,
        model=run_parameters.agent_llm,
        headless=True,
        raise_condition=RaiseCondition.NEVER,
        include_screenshot=run_parameters.include_screenshots,
        history_type=HistoryType(run_parameters.history_type),
    )

    _ = patcher.log_io(agent.llm, ["completion"])

    output = await agent.run(task_str)

    return cloudpickle.dumps(
        (
            task,
            RunOutput(
                success=output.success,
                answer=output.answer,
                trajectory=output.agent_trajectory,
                duration_in_s=time.time() - start,
                input_tokens=patcher.input_data,
                output_tokens=patcher.output_data,
            ),
        )
    )


def compute_tasks(run_parameters: RunParameters, monkeypatch) -> list[bytes]:
    tasks = load_webvoyager_data(WebVoyagerSubset.Simple)

    SUFFIX = "_CICD"
    for api_key_str in ["CEREBRAS_API_KEY", "OPENAI_API_KEY"]:

        api_key = os.environ.get(f"{api_key_str}{SUFFIX}")

        if api_key is None:
            logging.warning(f"CICD key for {api_key_str} not found, using default API key")
            api_key = os.environ.get(api_key_str)

        monkeypatch.setenv(api_key_str, api_key)

    browser_pool = None
    inputs = [
        (browser_pool, task, run_parameters, run_id)
        for task in tasks[:1]
        for run_id in range(run_parameters.tries_per_task)
    ]

    with concurrent.futures.ProcessPoolExecutor(max_workers=run_parameters.n_jobs) as executor:
        loop = asyncio.get_event_loop()
        futures = [loop.run_in_executor(executor, sync_wrapper, *inp) for inp in inputs]
        return loop.run_until_complete(asyncio.gather(*futures))


class LoggingSink:
    def __init__(self):
        self.messages: list[str] = []

    def write(self, message: str):
        message = message.strip()
        if message:
            self.messages.append(message)


def sync_wrapper(browser_pool: BrowserPool, task: WebVoyagerTask, run_parameters: RunParameters, run_id: int) -> bytes:
    """Wrapper for async function to run in a process."""

    loguru_logger.remove()
    sink = LoggingSink()
    loguru_logger.add(sink, level="DEBUG")  # Redirect loguru logs

    with contextlib.redirect_stdout(None), contextlib.redirect_stderr(None):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(run_agent(browser_pool, task, run_parameters))
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
            asyncio.set_event_loop(None)

    with open(f"dist/job_{task.name}_{task.id}_{run_id}.txt", "w") as f:
        _ = f.write("\n".join(sink.messages))

    return result


@pytest.mark.use_cli_args
@pytest.mark.timeout(60 * 60)  # fail after 1 hour
def test_benchmark_webvoyager(
    agent_llm: str, n_jobs: int, include_screenshots: bool, history_type: str, tries_per_task: int, monkeypatch
) -> None:
    run_parameters = RunParameters(
        agent_llm=agent_llm,
        n_jobs=n_jobs,
        include_screenshots=include_screenshots,
        history_type=history_type,
        tries_per_task=tries_per_task,
    )

    results = compute_tasks(run_parameters, monkeypatch)
    object_results = [cloudpickle.loads(result) for result in results]

    parsed_results = [
        parse_output(agent_llm, task, include_screenshots, run_output) for task, run_output in object_results
    ]

    df = pd.DataFrame((x.model_dump() for x in parsed_results)).sort_values(by=["task_website", "task_id"])

    filtered = df[DISPLAY_HTML_COLUMNS].copy()
    average_series = filtered.mean(numeric_only=True)
    average_series["task_website"] = "Average"
    filtered.loc["Average"] = average_series
    filtered["run_id"] = df.groupby(["task_website", "task_id"]).cumcount()
    filtered = filtered.fillna("")
    filtered = filtered.set_index(["task_website", "task_id", "run_id"])

    cols_to_display = [col for col in DISPLAY_MD_COLUMNS if col in filtered.columns]
    logging.info(f"\n\n{filtered[cols_to_display].to_markdown()}")

    os.makedirs("dist", exist_ok=True)

    with open(os.path.join("dist", "results.html"), "w") as f:
        param_text = f"""# Parameters

```json
{run_parameters.model_dump_json(indent=2)}
```

# Results
"""
        _ = f.write(param_text)

        _ = f.write(
            filtered.to_html(
                formatters={"replay_steps": format_html_code},
                escape=False,
                render_links=True,
                float_format="{:.1f}".format,
            )
        )

    df.to_json(os.path.join("dist", "results.jsonl"), orient="records", lines=True)

    assert df.success.all()


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


MessageElement = str | dict[str, str | dict[str, str]] | list["MessageElement"]


def get_textual_content(content: MessageElement, image_token_equivalent: int = 1000) -> list[str]:
    textual_content = []
    for message in content:
        if isinstance(message, str):
            textual_content.append(message)
        elif isinstance(message, list):
            textual_content.extend(get_textual_content(message))
        elif isinstance(message, dict):
            if "type" not in message:
                raise ValueError("Message is not a valid format")
            if message["type"] == "text":
                textual_content.append(message["text"])
            elif message["type"] == "image_url":
                placeholder = " ".join(("pass" for _ in range(image_token_equivalent)))
                textual_content.append(f"IMAGE[{placeholder}]")

    return textual_content


def parse_output(agent_key: str, task: WebVoyagerTask, include_screenshots: bool, run_output: RunOutput) -> TaskResult:
    encoding = tiktoken.get_encoding("cl100k_base")

    def get_content(message: dict[str, Any]) -> str:
        message = message["content"][0]
        if isinstance(message, str):
            return message
        return message["text"]

    input_messages = [json.loads(message) for message in run_output.input_tokens["LLMEngine.completion"]]
    input_tokens = [" ".join(get_textual_content([x["content"] for x in step["messages"]])) for step in input_messages]
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
        num_steps=len(run_output.trajectory),
        agent_answer=agent_answer,
        task=task,
        llm_calls=llm_calls,
        replay_steps=format_code(run_output),
    )

    return task_res


def format_code(run_output: RunOutput) -> str:
    LINE_TAG = "obs = await env.raw_step({action_name})"
    steps = []
    for step in run_output.trajectory:
        for result in step.results:
            action = result.input
            action_name = f"{action.__class__.__name__}.model_validate({action.model_dump_json()})".replace(
                "true", "True"
            ).replace("false", "False")
            steps.append(LINE_TAG.format(action_name=action_name))

    replay_steps = "\n".join(steps)
    return replay_steps
