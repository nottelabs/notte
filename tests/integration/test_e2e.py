import asyncio
import logging
import os
import time
import traceback
import typing
from typing import Any

import pandas as pd
import pytest
from joblib import Parallel, delayed

from eval.webvoyager.load_data import (
    WebVoyagerSubset,
    WebVoyagerTask,
    load_webvoyager_data,
)
from examples.simple.agent import SimpleAgent
from notte.browser.pool import BrowserPool


@pytest.fixture(scope="session")
def agent_llm(pytestconfig):
    return pytestconfig.getoption("agent_llm")


def run_agent(browser_pool: BrowserPool, agent_llm: str, task: WebVoyagerTask) -> dict[str, Any]:
    task_str = f"Your task: {task.question}. Use {task.url or 'the web'} to answer the question."

    async def _async_run():
        start = time.time()
        try:
            agent = SimpleAgent(model=agent_llm, headless=True, raise_on_failure=False)

            output = await agent.run(task_str)
            success = output.success

        except Exception as e:
            logging.error(f"Error running task: {task}: {e} {traceback.format_exc()}")
            success = False

        total_time = time.time() - start
        return {"website": task.name, "id": task.id, "success": success, "time": total_time}

    return asyncio.run(_async_run())


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
    results: list[dict[str, Any]] = typing.cast(
        list[dict[str, Any]],
        Parallel(n_jobs=-1)(delayed(run_agent)(browser_pool, agent_llm, task) for task in tasks[:1]),
    )
    results = sorted(results, key=lambda x: (x["website"], x["id"]))

    df = pd.DataFrame(results)
    logging.info(f"\n\n{df.to_markdown()}")
    assert all(result["success"] for result in results)
