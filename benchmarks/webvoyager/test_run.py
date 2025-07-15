import json
import os
from typing import Any

import pytest
from bench_types import (  # pyright: ignore[reportImplicitRelativeImport]
    BenchmarkTask,
    RunOutput,
    TaskResult,
)
from evaluator import EvaluationResponse, Evaluator  # pyright: ignore[reportImplicitRelativeImport]
from loguru import logger
from run import (  # pyright: ignore[reportImplicitRelativeImport]
    evaluate,
    process_output,
    read_tasks,
    run_task_with_session,
)
from webvoyager import WebvoyagerEvaluator  # pyright: ignore[reportImplicitRelativeImport]

webvoyager_tasks = read_tasks(
    "packages/notte-eval/src/notte_eval/data/webvoyager/webvoyager_simple.jsonl", 5
)  # second param is number of runs per task


@pytest.fixture(scope="module")
def model() -> str:
    return "vertex_ai/gemini-2.5-flash"


@pytest.fixture(scope="module")
def evaluator(model: str) -> Evaluator:
    return WebvoyagerEvaluator(model=model)  # pytright: ignore[reportUnknownParameterType, reportMissingParameterType]


@pytest.mark.asyncio
@pytest.mark.parametrize("task_tuple", webvoyager_tasks)
async def test_run(task_tuple: tuple[BenchmarkTask, int], evaluator: Evaluator, model: str):
    try:
        task = task_tuple[0]
        run_num = task_tuple[1]

        resp: RunOutput = await run_task_with_session(task=task, headless=True, model=model)
        out: TaskResult = await process_output(task=task, out=resp)
        eval: EvaluationResponse = await evaluate(evaluator, out)
        logger.info(f"Eval Result: {eval}")

        output_dir = f"raw_output_data/{task.id}/"
        os.makedirs(output_dir, exist_ok=True)
        output_dict: dict[str, Any] = {
            "task": task.model_dump(),
            "response": out.convert_to_dict,
            "eval": eval.model_dump(),
            "run": run_num,
        }
        out.screenshots.get().save(f"{output_dir}{task.id}--{run_num}.webp")

        with open(f"{output_dir}output--{run_num}.json", "w") as f:
            json.dump(output_dict, f)
    except Exception as e:
        logger.info(f"An exception occured: {e}")
