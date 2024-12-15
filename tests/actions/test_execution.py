import asyncio
from dataclasses import dataclass

import pytest

from notte.env import NotteEnv
from tests.mock.mock_service import MockLLMService


def headless() -> bool:
    return True


@dataclass
class StepArgs:
    action_id: str
    value: str | None


@dataclass
class ExecutionTest:
    url: str
    steps: list[StepArgs]


@pytest.fixture
def phantombuster_login() -> ExecutionTest:
    return ExecutionTest(
        url="https://phantombuster.com/login",
        steps=[
            StepArgs(action_id="I1", value="lucasgiordano@gmail.com"),
            StepArgs(action_id="I2", value="lucasgiordano"),
            StepArgs(action_id="B7", value=None),
        ],
    )


async def _test_execution(test: ExecutionTest, headless: bool = True) -> None:
    async with NotteEnv(headless=headless, llmserve=MockLLMService(mock_response="")) as env:
        _ = await env.goto(test.url)
        for step in test.steps:
            _ = await env.execute(step.action_id, step.value, enter=False)


def test_execution(phantombuster_login: ExecutionTest) -> None:
    asyncio.run(_test_execution(phantombuster_login))
