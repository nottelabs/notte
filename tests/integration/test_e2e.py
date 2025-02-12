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
from examples.simple.agent import SimpleAgent
from notte.browser.pool import BrowserPool


class RunOutput(BaseModel):
    success: bool
    answer: str
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


def run_agent(browser_pool: BrowserPool, agent_llm: str, task: WebVoyagerTask) -> tuple[WebVoyagerTask, RunOutput]:
    task_str = f"Your task: {task.question}. Use {task.url or 'the web'} to answer the question."
    start = time.time()
    patcher = AgentPatcher()

    async def _async_run():
        try:
            agent = SimpleAgent(pool=browser_pool, model=agent_llm, headless=True, raise_on_failure=False)

            _ = patcher.log_io(agent.llm, ["completion"])

            output = await agent.run(task_str)

            return output, patcher

        except Exception as e:
            logging.error(f"Error running task: {task}: {e} {traceback.format_exc()}")

        return None, patcher

    output, patcher = asyncio.run(_async_run())

    if output is not None:
        success = output.success
        answer = output.answer
        num_steps = len(output.trajectory)
    else:
        success = False
        answer = ""

        # assume as many llm calls as there are steps
        num_steps = len(patcher.input_data["LLMEngine.completion"])

    return task, RunOutput(
        success=success,
        answer=answer,
        num_steps=num_steps,
        duration_in_s=time.time() - start,
        input_tokens=patcher.input_data,
        output_tokens=patcher.output_data,
    )

    return task, asyncio.run(_async_run())


@pytest.mark.timeout(60 * 60 * 2)  # fail after 2 hours
@pytest.mark.asyncio
async def test_benchmark_webvoyager(agent_llm: str, monkeypatch) -> None:
    tasks = load_webvoyager_data(WebVoyagerSubset.Simple)

    api_key = os.environ.get("CEREBRAS_API_KEY_CICD")

    if api_key is None:
        logging.warning("Cerebras API key not found, using default API key")
        api_key = os.environ.get("CEREBRAS_API_KEY")

    monkeypatch.setenv("CEREBRAS_API_KEY", api_key)

    browser_pool = BrowserPool()
    results: list[tuple[WebVoyagerTask, RunOutput]] = typing.cast(
        list[tuple[WebVoyagerTask, RunOutput]],
        Parallel(n_jobs=2)(delayed(run_agent)(browser_pool, agent_llm, task) for task in tasks[:2]),
    )

    parsed_results = [parse_output(agent_llm, task, run_output) for task, run_output in results]

    df = pd.DataFrame((x.model_dump() for x in parsed_results)).sort_values(by=["task_website", "task_id"])
    filtered = df[
        [
            "task_website",
            "task_id",
            "success",
            "duration_in_s",
            "num_steps",
            "total_input_tokens",
            "total_output_tokens",
        ]
    ].copy()
    filtered.loc["Average"] = filtered.mean(numeric_only=True)
    filtered = filtered.fillna("")

    logging.info(f"\n\n{filtered.to_markdown()}")

    os.makedirs("dist", exist_ok=True)

    filtered.to_markdown(os.path.join("dist", "results.md"))
    df.to_json(os.path.join("dist", "results.jsonl"), orient="records", lines=True)

    assert df.success.all()


def parse_output(agent_key: str, task: WebVoyagerTask, run_output: RunOutput) -> TaskResult:
    encoding = tiktoken.get_encoding("cl100k_base")

    input_messages = [json.loads(message) for message in run_output.input_tokens["LLMEngine.completion"]]
    input_tokens = [" ".join(message["content"] for message in step["messages"]) for step in input_messages]
    num_inputs_per_step = [len(encoding.encode(tokens)) for tokens in input_tokens]

    output_messages = [json.loads(message) for message in run_output.output_tokens["LLMEngine.completion"]]
    output_tokens = [step["choices"][0]["message"]["content"] for step in output_messages]
    num_outputs_per_step = [len(encoding.encode(tokens)) for tokens in output_tokens]

    try:
        agent_answer = run_output.output.answer
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
    )

    return task_res
