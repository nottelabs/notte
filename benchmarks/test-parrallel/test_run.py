import json
import os

import pytest
from loguru import logger
from run import (  # pyright: ignore[reportImplicitRelativeImport]
    evaluate,
    process_output,
    read_tasks,
    run_task_with_session,
)
from webvoyager import WebvoyagerEvaluator  # pyright: ignore[reportImplicitRelativeImport]

webvoyager_tasks = read_tasks("benchmarks/test-parrallel/data/webvoyager_simple.jsonl")


@pytest.fixture(scope="module")
def evaluator():
    return WebvoyagerEvaluator()


@pytest.mark.asyncio
@pytest.mark.parametrize("task", webvoyager_tasks)
async def test_run(task, evaluator):  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
    try:
        resp = await run_task_with_session(task=task, headless=True, model="vertex_ai/gemini-2.5-flash")  # pyright: ignore[reportUnknownArgumentType]
        out = await process_output(task=task, out=resp)  # pyright: ignore[reportUnknownArgumentType]
        eval = await evaluate(evaluator, out)  # pyright: ignore[reportUnknownArgumentType]
        logger.info(f"Eval Result: {eval}")

        output_dir = f"raw_output_data/{task.id}/"  # pyright: ignore[reportUnknownMemberType]
        os.makedirs(output_dir, exist_ok=True)
        output_dict = {"response": out.convert_to_dict, "eval": eval.model_dump()}
        out.screenshots.get().save(f"{output_dir}{task.id}.webp")  # pyright: ignore[reportUnknownMemberType]

        with open(f"{output_dir}output.json", "w") as f:
            json.dump(output_dict, f)
    except Exception as e:
        logger.info(f"An exception occured: {e}")
