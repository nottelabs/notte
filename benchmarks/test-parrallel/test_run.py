import json
import os

import pytest
from loguru import logger
from notte_eval.evaluators.webvoyager import WebvoyagerEvaluator
from run import (  # pyright: ignore[reportImplicitRelativeImport]
    evaluate,
    process_output,
    read_tasks,
    run_task_with_session,
)

import notte

tasks = [
    {
        "task": "find the top news headline",
        "url": "https://news.google.com",
    },
    {
        "task": "find a linear algebra meme",
        "url": "https://findthatmeme.com/",
    },
    {
        "task": "find out where steve jobs was born",
        "url": "https://wikipedia.org",
    },
    {
        "task": "get the current temperature in New York City",
        "url": "https://weather.gov",
    },
    {
        "task": "look up the definition of 'entropy'",
        "url": "https://www.merriam-webster.com",
    },
    {
        "task": "find the current price of TSLA stock",
        "url": "https://finance.yahoo.com/",
    },
    {
        "task": "check the latest post on Hacker News",
        "url": "https://news.ycombinator.com",
    },
]


webvoyager_tasks = read_tasks("benchmarks/test-parrallel/data/webvoyager_single.jsonl")


@pytest.fixture(scope="module")
def session():
    sess = notte.Session(headless=True)
    sess.start()
    yield sess

    sess.stop()


@pytest.fixture(scope="module")
def evaluator():
    return WebvoyagerEvaluator()


@pytest.mark.asyncio
@pytest.mark.parametrize("task", webvoyager_tasks)
async def test_run(task, evaluator):  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
    resp = await run_task_with_session(task=task, headless=True, model="gemini/gemini-2.0-flash")  # pyright: ignore[reportUnknownArgumentType]
    out = await process_output(task=task, out=resp)  # pyright: ignore[reportUnknownArgumentType]
    eval = await evaluate(evaluator, out)  # pyright: ignore[reportUnknownArgumentType]
    logger.info(f"Eval Result: {eval}")

    output_dir = f"raw_output_data/{task.id}/"  # pyright: ignore[reportUnknownMemberType]
    os.makedirs(output_dir)
    output_dict = {"response": out.convert_to_dict, "eval": eval.model_dump()}
    out.screenshots.get().save(f"{output_dir}{task.id}.webp")  # pyright: ignore[reportUnknownMemberType]

    with open(f"{output_dir}output.json", "w") as f:
        json.dump(output_dict, f)
