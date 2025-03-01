import asyncio
from dataclasses import dataclass

import pytest

from notte.browser.window import BrowserWindowConfig
from notte.env import NotteEnv, NotteEnvConfig
from tests.mock.mock_service import MockLLMService


@pytest.fixture
def headless() -> bool:
    return True


@dataclass
class StepArgs:
    action_id: str
    value: str | None
    enter: bool = False


@dataclass
class ExecutionTest:
    url: str
    steps: list[StepArgs]


@pytest.fixture
def phantombuster_login() -> ExecutionTest:
    return ExecutionTest(
        url="https://phantombuster.com/login",
        steps=[
            StepArgs(action_id="B4", value=None, enter=False),
            StepArgs(action_id="I1", value="lucasgiordano@gmail.com", enter=False),
            StepArgs(action_id="I2", value="lucasgiordano", enter=False),
            StepArgs(action_id="B2", value=None, enter=False),
        ],
    )


async def _test_execution(test: ExecutionTest, headless: bool) -> None:
    async with NotteEnv(
        NotteEnvConfig(window=BrowserWindowConfig(headless=headless)),
        llmserve=MockLLMService(mock_response=""),
    ) as env:
        _ = await env.goto(test.url)
        for step in test.steps:
            if not env.snapshot.dom_node.find(step.action_id):
                inodes = [(n.id, n.text) for n in env.snapshot.interaction_nodes()]
                raise ValueError(f"Action {step.action_id} not found in context with interactions {inodes}")
            _ = await env.execute(step.action_id, step.value, enter=step.enter)


def test_execution(phantombuster_login: ExecutionTest, headless: bool) -> None:
    asyncio.run(_test_execution(phantombuster_login, headless))
