import os
import time
import traceback

import pandas as pd
import pytest
from loguru import logger

from eval.webvoyager.load_data import WebVoyagerSubset, load_webvoyager_data
from examples.simple.agent import SimpleAgent


@pytest.fixture(scope="session")
def agent_llm(pytestconfig):
    return pytestconfig.getoption("agent_llm")


@pytest.mark.timeout(60 * 60 * 2)  # fail after 2 hours
@pytest.mark.asyncio
async def test_benchmark_webvoyager(agent_llm: str, monkeypatch) -> None:
    tasks = load_webvoyager_data(WebVoyagerSubset.Simple)

    api_key = os.environ.get("CEREBRAS_API_KEY_CICD")

    if api_key is None:
        logger.warning("Cerebras API key not found, using default API key")
        api_key = os.environ.get("CEREBRAS_API_KEY")

    monkeypatch.setenv("CEREBRAS_API_KEY", api_key)

    results = []

    for task in tasks:
        start = time.time()
        try:
            agent = SimpleAgent(model=agent_llm, headless=True, raise_on_failure=False)
            output = await agent.run(f"Your task: {task.question}. Use {task.url or 'the web'} to answer the question.")
            logger.info(f"Output: {output}")
            success = output.success

        except Exception as e:
            logger.error(f"Error running task: {task}: {e} {traceback.format_exc()}")
            success = False

        total_time = time.time() - start
        results.append({"website": task.name, "id": task.id, "success": success, "time": total_time})

    df = pd.DataFrame(results)
    print(df.to_markdown())
    assert all(result["success"] for result in results)
