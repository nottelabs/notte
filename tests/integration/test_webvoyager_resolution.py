import pytest

from notte_eval.webvoyager.load_data import load_webvoyager_data
from tests.integration.test_resolution import _test_action_node_resolution_pipe


def get_webvoyager_urls() -> list[str]:
    return list(set([task.url for task in load_webvoyager_data()]))


@pytest.mark.asyncio
@pytest.mark.parametrize("url", get_webvoyager_urls())
async def test_webvoyager_resolution(url: str) -> None:
    await _test_action_node_resolution_pipe(url)
