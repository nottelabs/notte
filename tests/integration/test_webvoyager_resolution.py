import pytest
from notte_eval.data.load_data import WebVoyagerTask

from tests.integration.test_resolution import test_action_node_resolution_pipe


def get_webvoyager_urls() -> list[str]:
    tasks = WebVoyagerTask.read_tasks()
    return list(set([task.url for task in tasks]))


@pytest.mark.asyncio
@pytest.mark.parametrize("url", get_webvoyager_urls())
async def test_webvoyager_resolution(url: str) -> None:
    await test_action_node_resolution_pipe(url)
