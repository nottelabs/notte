import json
import os
import traceback
from typing import Any

import pytest
from _pytest.python import Metafunc
from loguru import logger
from notte_sdk import NotteClient

from notte_eval.evaluators.evaluator import EvaluationResponse, Evaluator
from notte_eval.evaluators.webvoyager import WebvoyagerEvaluator
from notte_eval.webvoyager.bench_types import (
    BenchmarkTask,
    RunOutput,
    RunParams,
    SdkRunOutput,
    SdkTaskResult,
    TaskResult,
)
from notte_eval.webvoyager.run import (
    evaluate,
    process_output,
    process_output_sdk,
    read_tasks,
    run_task_with_sdk,
    run_task_with_session,
)


@pytest.fixture(scope="module")
def run_params(pytestconfig: pytest.Config) -> RunParams:
    params = {}

    ua_str: str = pytestconfig.getoption("user_agent")  # pyright: ignore[reportAssignmentType]
    ms_str: str = pytestconfig.getoption("max_steps")  # pyright: ignore[reportAssignmentType]

    params["model"] = pytestconfig.getoption("model")
    params["use_sdk"] = pytestconfig.getoption("use_sdk") == "true"
    params["headless"] = pytestconfig.getoption("headless") == "true"
    params["use_vision"] = pytestconfig.getoption("use_vision") == "true"
    params["max_steps"] = int(ms_str)
    params["proxies"] = pytestconfig.getoption("proxies") == "true"
    params["user_agent"] = None if ua_str == "" else ua_str

    return RunParams.model_validate(params)


@pytest.fixture(scope="module")
def evaluator(run_params: RunParams) -> Evaluator:
    return WebvoyagerEvaluator(
        model=run_params.model
    )  # pytright: ignore[reportUnknownParameterType, reportMissingParameterType]


@pytest.fixture(scope="module")
def client() -> NotteClient:
    return NotteClient()


def pytest_generate_tests(metafunc: Metafunc):
    task_dir: str = metafunc.config.getoption("task_dir")  # pyright: ignore[reportAssignmentType]
    n_runs: str = metafunc.config.getoption("n_runs")  # pyright: ignore[reportAssignmentType]

    webvoyager_tasks = read_tasks("packages/notte-eval/src/notte_eval/data/" + task_dir, int(n_runs))

    metafunc.parametrize("task_tuple", webvoyager_tasks)


@pytest.mark.asyncio
async def test_run(
    task_tuple: tuple[BenchmarkTask, int], evaluator: Evaluator, client: NotteClient, run_params: RunParams
):
    task = task_tuple[0]
    run_num = task_tuple[1]
    output_dir = f"raw_output_data/{task.id}/"
    os.makedirs(output_dir, exist_ok=True)

    try:
        if run_params.use_sdk:
            sdk_resp: SdkRunOutput = await run_task_with_sdk(
                task=task,
                client=client,
                headless=run_params.headless,
                model=run_params.model,
                use_vision=run_params.use_vision,
                max_steps=run_params.max_steps,
                proxies=run_params.proxies,
                user_agent=run_params.user_agent,
            )
            out: SdkTaskResult | TaskResult = await process_output_sdk(task=task, out=sdk_resp)  # pyright: ignore[reportRedeclaration]

        else:
            resp: RunOutput = await run_task_with_session(
                task=task,
                headless=run_params.headless,
                model=run_params.model,
                use_vision=run_params.use_vision,
                max_steps=run_params.max_steps,
                user_agent=run_params.user_agent,
            )
            out: SdkTaskResult | TaskResult = await process_output(task=task, out=resp)

        eval: EvaluationResponse = await evaluate(evaluator, out)
        logger.info(f"Eval Result: {eval}")

        output_dict: dict[str, Any] = {
            "task": task.model_dump(),
            "params": run_params.model_dump(),
            "response": out.convert_to_dict,
            "eval": eval.model_dump(),
            "run": run_num,
        }
        out.screenshots.get().save(f"{output_dir}{task.id}--{run_num}.webp")

        with open(f"{output_dir}output--{run_num}.json", "w") as f:
            json.dump(output_dict, f, default=str)
    except Exception as e:
        logger.info(f"An exception occurred: {e}")

        with open(f"{output_dir}error--{run_num}.txt", "w") as f:
            _ = f.write(traceback.format_exc())
